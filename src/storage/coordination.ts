import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";
import { existsSync, fsyncSync, mkdirSync, openSync, closeSync } from "node:fs";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { CoreError } from "../core/contracts.ts";

export type PhaseKind = "read" | "mutate" | "settle" | "maintenance";
export interface PhaseOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  operationId?: string;
}
export type CommandKind = PhaseKind;
export type OperationOptions = PhaseOptions;
export interface Reservation {
  operation_id: string;
  epoch: string;
  session_id?: string;
  kind: string;
  digest: string;
  resources: string[];
  metadata?: Record<string, unknown>;
}
export interface Operation extends Reservation {
  runtime_id: string;
  phase: string;
  status: "active" | "unknown" | "settled";
  created_at: string;
  updated_at: string;
}
interface RuntimeRow {
  runtime_id: string;
  lease_name: string;
  status: "alive" | "dead" | "unknown";
}
interface Waiter {
  ticket: number;
  waiter_id: string;
  runtime_id: string;
  kind: PhaseKind;
  operation_id: string | null;
  deadline: number;
}
interface Maintenance {
  mode: "normal" | "draining" | "exclusive";
  runtime_id: string | null;
  token: string | null;
  kind: string | null;
  expected_epoch: string | null;
}
interface Capability {
  readonly token: object;
  active: boolean;
  kind: PhaseKind;
  probes: DatabaseSync[];
  provenDead: Set<string>;
  invoked: boolean;
}

// A cancelled/paused pre-admission request must not strand a live runtime's
// FIFO ticket. Expiration never applies to admitted callbacks or reservations.
const WAITER_TTL_MS = 1000;
function failure(code: string, message: string): never {
  throw new CoreError(code, message);
}
function busy(message: string): never {
  return failure("STORE_BUSY", message);
}
function sqliteBusy(error: unknown) {
  const value = error as { code?: string; errcode?: number; message?: string };
  return (
    (value.errcode !== undefined && [5, 6].includes(value.errcode & 255)) ||
    value.code === "SQLITE_BUSY" ||
    value.code === "SQLITE_LOCKED" ||
    /database (?:is )?(?:locked|busy)/i.test(value.message ?? "")
  );
}
function configure(db: DatabaseSync) {
  db.exec(
    "PRAGMA busy_timeout=0; PRAGMA locking_mode=NORMAL; PRAGMA synchronous=FULL;",
  );
  const mode = db.prepare("PRAGMA journal_mode").get() as {
    journal_mode: string;
  };
  if (mode.journal_mode.toLowerCase() !== "delete")
    failure("STORE_UNAVAILABLE", "Coordination requires DELETE journal mode.");
}
function jsonOperation(row: { json: string } | undefined) {
  return row ? (JSON.parse(row.json) as Operation) : undefined;
}
function assertReservation(value: Reservation) {
  if (
    !value ||
    ![value.operation_id, value.epoch, value.kind, value.digest].every(
      (part) => typeof part === "string" && part.length > 0,
    ) ||
    (value.session_id !== undefined && typeof value.session_id !== "string") ||
    (value.metadata !== undefined &&
      (value.metadata === null ||
        typeof value.metadata !== "object" ||
        Array.isArray(value.metadata))) ||
    !Array.isArray(value.resources) ||
    !value.resources.every((key) => typeof key === "string" && key.length > 0)
  )
    failure("VALIDATION_ERROR", "Invalid operation reservation metadata.");
}

/**
 * A stable database serializes complete synchronous Core phases. A different,
 * unique SQLite file owns each runtime's lifetime OS lock. PID and wall-clock
 * age never establish that a runtime is dead.
 */
export class Coordination {
  readonly identity: string;
  readonly runtimeId: string;
  readonly path: string;
  private readonly db: DatabaseSync;
  private lease!: DatabaseSync;
  private readonly leaseName: string;
  private readonly scope = new AsyncLocalStorage<Capability>();
  private transaction = false;
  private closed = false;
  private registered = false;
  private waiting = 0;
  private readonly stats = { admitted: 0, busy: 0, cancelled: 0 };

  constructor(
    readonly controlHome: string,
    runtimeId: string = randomUUID(),
    options: { expectedId?: string; create?: boolean } = {},
  ) {
    if (!/^[A-Za-z0-9_-]{1,128}$/.test(runtimeId))
      failure("VALIDATION_ERROR", "Invalid runtime identity.");
    this.runtimeId = runtimeId;
    this.path = join(controlHome, "coordination.sqlite");
    this.leaseName = `${runtimeId}.sqlite`;
    const existed = existsSync(this.path);
    if (!existed && (options.create === false || options.expectedId))
      failure(
        "STORE_UNAVAILABLE",
        "Known coordination database is missing; preserve the workspace.",
      );
    mkdirSync(controlHome, { recursive: true });
    this.db = new DatabaseSync(this.path);
    let leaseCreated = false;
    try {
      configure(this.db);
      const hasMeta = this.db
        .prepare(
          "SELECT name FROM sqlite_master WHERE type='table' AND name='identitymeta'",
        )
        .get();
      if (!hasMeta) {
        if (existed && options.create !== true)
          failure(
            "STORE_UNAVAILABLE",
            "Existing coordination database has no recognized identity.",
          );
        this.db.exec("BEGIN IMMEDIATE");
        const racedInitialization = this.db
          .prepare(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='identitymeta'",
          )
          .get();
        if (!racedInitialization) {
          const unexpected = this.db
            .prepare(
              "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
            )
            .all();
          if (unexpected.length)
            failure(
              "STORE_UNAVAILABLE",
              "Unrecognized coordination tables; preserve the existing database.",
            );
          this.db
            .exec(`CREATE TABLE identitymeta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE runtimes(runtime_id TEXT PRIMARY KEY,lease_name TEXT NOT NULL UNIQUE,status TEXT NOT NULL,created_at TEXT NOT NULL);
          CREATE TABLE waiters(ticket INTEGER PRIMARY KEY AUTOINCREMENT,waiter_id TEXT NOT NULL UNIQUE,runtime_id TEXT NOT NULL,kind TEXT NOT NULL,operation_id TEXT,deadline INTEGER NOT NULL);
          CREATE TABLE operations(operation_id TEXT PRIMARY KEY,runtime_id TEXT NOT NULL,status TEXT NOT NULL,json TEXT NOT NULL);
          CREATE TABLE resource_reservations(resource TEXT NOT NULL,operation_id TEXT NOT NULL,PRIMARY KEY(resource,operation_id));
          CREATE INDEX reservation_operation ON resource_reservations(operation_id);
          CREATE TABLE maintenance(singleton INTEGER PRIMARY KEY CHECK(singleton=1),mode TEXT NOT NULL,runtime_id TEXT,token TEXT,kind TEXT,expected_epoch TEXT);
          INSERT INTO maintenance(singleton,mode) VALUES(1,'normal');`);
          this.db
            .prepare(
              "INSERT INTO identitymeta(key,value) VALUES('identity',?),('format','1')",
            )
            .run(randomUUID());
        }
        this.db.exec("COMMIT");
      }
      const meta = this.db
        .prepare("SELECT value FROM identitymeta WHERE key='identity'")
        .get() as { value: string } | undefined;
      const format = this.db
        .prepare("SELECT value FROM identitymeta WHERE key='format'")
        .get() as { value: string } | undefined;
      if (
        !meta?.value ||
        format?.value !== "1" ||
        (options.expectedId && options.expectedId !== meta.value)
      )
        failure(
          "STORE_UNAVAILABLE",
          "Coordination identity/format does not match the trusted control root.",
        );
      this.identity = meta.value;
      mkdirSync(join(controlHome, "runtimes"), { recursive: true });
      // Exclusive create prevents UUID reuse and never removes a foreign lease.
      const fd = openSync(join(controlHome, "runtimes", this.leaseName), "wx");
      try {
        fsyncSync(fd);
      } finally {
        closeSync(fd);
      }
      this.lease = new DatabaseSync(
        join(controlHome, "runtimes", this.leaseName),
      );
      leaseCreated = true;
      configure(this.lease);
      this.lease.exec("CREATE TABLE lease(identity TEXT NOT NULL);");
      this.lease
        .prepare("INSERT INTO lease(identity) VALUES(?)")
        .run(runtimeId);
      this.lease.exec("BEGIN IMMEDIATE");
    } catch (error) {
      try {
        this.db.exec("ROLLBACK");
      } catch {
        /* No active initialization. */
      }
      if (leaseCreated) this.lease.close();
      this.db.close();
      if (sqliteBusy(error))
        busy("Coordination is busy during startup; retry asynchronously.");
      throw error;
    }
  }

  get held() {
    return (
      !this.closed && this.transaction && this.scope.getStore()?.active === true
    );
  }
  get phaseToken(): object | undefined {
    return this.held ? this.scope.getStore()!.token : undefined;
  }
  assertHeld() {
    if (!this.held)
      failure(
        "STORE_BUSY",
        "This Core phase has no live coordination capability.",
      );
  }
  private assertOpen() {
    if (this.closed)
      failure("STORE_UNAVAILABLE", "Coordination runtime is closed.");
    const inherited = this.scope.getStore();
    if (inherited && !inherited.active)
      failure("STORE_BUSY", "The coordination capability has been revoked.");
  }
  private register() {
    if (this.registered) return;
    this.db
      .prepare(
        "INSERT INTO runtimes(runtime_id,lease_name,status,created_at) VALUES(?,?,'alive',?)",
      )
      .run(this.runtimeId, this.leaseName, new Date().toISOString());
    // The flag is set only after COMMIT, below; rollback must permit retry.
  }
  private maintenanceState(): Maintenance {
    return this.db
      .prepare(
        "SELECT mode,runtime_id,token,kind,expected_epoch FROM maintenance WHERE singleton=1",
      )
      .get() as unknown as Maintenance;
  }
  /** Trusted startup recovery only. Never include this token in owner/tool diagnostics. */
  maintenanceInfo(): Maintenance {
    this.assertOpen();
    try {
      return this.maintenanceState();
    } catch (error) {
      if (sqliteBusy(error))
        busy(
          "Maintenance metadata is temporarily busy; retry startup recovery asynchronously.",
        );
      throw error;
    }
  }
  private eligible(kind: PhaseKind, operationId?: string) {
    const state = this.maintenanceState();
    if (state.mode === "normal") return true;
    if (kind === "maintenance" && state.runtime_id === this.runtimeId)
      return true;
    if (state.mode === "exclusive") return false;
    if (kind === "read") return true;
    if (kind !== "settle" || !operationId) return false;
    const op = this.lookup(operationId);
    return op?.runtime_id === this.runtimeId && op.status !== "settled";
  }
  private waiterEligible(waiter: Waiter) {
    const state = this.maintenanceState();
    if (state.mode === "normal") return true;
    if (waiter.kind === "maintenance" && state.runtime_id === waiter.runtime_id)
      return true;
    if (state.mode === "exclusive") return false;
    if (waiter.kind === "read") return true;
    if (waiter.kind !== "settle" || !waiter.operation_id) return false;
    const op = this.lookup(waiter.operation_id);
    return op?.runtime_id === waiter.runtime_id && op.status !== "settled";
  }
  private lookup(id: string) {
    return jsonOperation(
      this.db
        .prepare("SELECT json FROM operations WHERE operation_id=?")
        .get(id) as { json: string } | undefined,
    );
  }
  private save(operation: Operation) {
    this.db
      .prepare(
        "INSERT INTO operations(operation_id,runtime_id,status,json) VALUES(?,?,?,?) ON CONFLICT(operation_id) DO UPDATE SET runtime_id=excluded.runtime_id,status=excluded.status,json=excluded.json",
      )
      .run(
        operation.operation_id,
        operation.runtime_id,
        operation.status,
        JSON.stringify(operation),
      );
  }
  private invoke<T>(fn: () => T): T {
    this.scope.getStore()!.invoked = true;
    const result = fn();
    if (result && typeof (result as { then?: unknown }).then === "function") {
      // An async callback's continuations retain a revoked capability and fail
      // assertHeld. Observe its rejection to avoid an unhandled Promise.
      void Promise.resolve(result).catch(() => {});
      failure(
        "VALIDATION_ERROR",
        "A coordination phase must be synchronous; await outside the gate.",
      );
    }
    return result;
  }
  private enter<T>(fn: () => T, kind: PhaseKind): T {
    this.db.exec("BEGIN IMMEDIATE");
    this.transaction = true;
    const cap: Capability = {
      token: Object.freeze({}),
      active: true,
      kind,
      probes: [],
      provenDead: new Set(),
      invoked: false,
    };
    try {
      const result = this.scope.run(cap, () => {
        this.register();
        return fn();
      });
      try {
        // Competing BEGIN IMMEDIATE attempts can briefly hold a SHARED lock.
        // Retry only COMMIT, never the admitted callback, without yielding
        // the gate or installing a SQLite busy timeout.
        const commitDeadline = performance.now() + 25;
        for (;;) {
          try {
            this.db.exec("COMMIT");
            break;
          } catch (error) {
            if (!sqliteBusy(error) || performance.now() >= commitDeadline)
              throw error;
          }
        }
      } catch (error) {
        if (sqliteBusy(error) && cap.invoked)
          busy(
            "Coordination commit could not complete; do not redispatch this phase without reconciliation.",
          );
        throw error;
      }
      this.registered = true;
      return result;
    } catch (error) {
      try {
        this.db.exec("ROLLBACK");
      } catch {
        /* Preserve the original failure. */
      }
      if (cap.invoked && sqliteBusy(error))
        busy(
          "An admitted Core phase encountered contention; reconcile its outcome before retrying.",
        );
      throw error;
    } finally {
      cap.active = false;
      this.transaction = false;
      // Dead-runtime proofs remain locked until their marking/adoption commits.
      for (const probe of cap.probes) {
        try {
          probe.exec("ROLLBACK");
        } finally {
          probe.close();
        }
      }
    }
  }
  private checkRequest(options: PhaseOptions, deadline: number) {
    this.assertOpen();
    if (options.signal?.aborted) {
      this.stats.cancelled++;
      failure(
        "STORE_CANCELLED",
        "Coordination request was cancelled before admission.",
      );
    }
    if (Date.now() >= deadline)
      busy("Coordination request timed out before admission.");
  }
  private deadline(options: PhaseOptions) {
    const timeout = options.timeoutMs ?? 30_000;
    if (!Number.isFinite(timeout) || timeout < 0)
      failure(
        "VALIDATION_ERROR",
        "Coordination timeout must be a finite nonnegative number.",
      );
    return Date.now() + timeout;
  }
  private head(): Waiter | undefined {
    const rows = this.db
      .prepare("SELECT * FROM waiters ORDER BY ticket")
      .all() as unknown as Waiter[];
    for (const waiter of rows) {
      if (
        waiter.deadline <= Date.now() ||
        this.probeRuntime(waiter.runtime_id) === "dead"
      ) {
        this.db
          .prepare("DELETE FROM waiters WHERE waiter_id=?")
          .run(waiter.waiter_id);
        continue;
      }
      if (this.waiterEligible(waiter)) return waiter;
    }
    return undefined;
  }
  sync<T>(kind: PhaseKind, fn: () => T, options: PhaseOptions = {}): T {
    this.assertOpen();
    if (options.signal?.aborted)
      failure(
        "STORE_CANCELLED",
        "Coordination request was cancelled before admission.",
      );
    if (this.held) {
      if (this.scope.getStore()!.kind === "read" && kind !== "read")
        failure(
          "VALIDATION_ERROR",
          "A read phase cannot escalate its capability.",
        );
      return this.invoke(fn);
    }
    try {
      return this.enter(() => {
        if (!this.eligible(kind, options.operationId) || this.head())
          busy("Coordination admission is queued or fenced by maintenance.");
        this.stats.admitted++;
        return this.invoke(fn);
      }, kind);
    } catch (error) {
      if (sqliteBusy(error)) {
        this.stats.busy++;
        busy(
          "Another runtime holds the complete Core phase; retry asynchronously.",
        );
      }
      throw error;
    }
  }
  async run<T>(
    kind: PhaseKind,
    fn: () => T,
    options: PhaseOptions = {},
  ): Promise<T> {
    this.assertOpen();
    if (this.held) return this.sync(kind, fn, options);
    const deadline = this.deadline(options);
    const waiterId = randomUUID();
    let queued = false;
    this.waiting++;
    try {
      for (;;) {
        this.checkRequest(options, deadline);
        try {
          if (!queued) {
            this.enter(() => {
              this.db
                .prepare(
                  "INSERT INTO waiters(waiter_id,runtime_id,kind,operation_id,deadline) VALUES(?,?,?,?,?)",
                )
                .run(
                  waiterId,
                  this.runtimeId,
                  kind,
                  options.operationId ?? null,
                  Math.min(deadline, Date.now() + WAITER_TTL_MS),
                );
            }, kind);
            queued = true;
          }
          const admitted = this.enter(() => {
            this.checkRequest(options, deadline);
            const ownWaiter = this.db
              .prepare("SELECT waiter_id FROM waiters WHERE waiter_id=?")
              .get(waiterId);
            if (!ownWaiter) return { done: false as const, missing: true };
            this.db
              .prepare("UPDATE waiters SET deadline=? WHERE waiter_id=?")
              .run(Math.min(deadline, Date.now() + WAITER_TTL_MS), waiterId);
            if (this.head()?.waiter_id !== waiterId)
              return { done: false as const, missing: false };
            this.db
              .prepare("DELETE FROM waiters WHERE waiter_id=?")
              .run(waiterId);
            this.stats.admitted++;
            return { done: true as const, result: this.invoke(fn) };
          }, kind);
          if (admitted.done) return admitted.result;
          if (admitted.missing) queued = false;
        } catch (error) {
          if (!sqliteBusy(error)) throw error;
          this.stats.busy++;
        }
        await this.pause(
          options.signal,
          Math.min(
            6 + Math.floor(Math.random() * 19),
            Math.max(1, deadline - Date.now()),
          ),
        );
      }
    } finally {
      this.waiting--;
      // A BUSY cleanup is harmless: its deadline and lease remain durable. A
      // cancellation is never allowed to delete a waiter that has been admitted.
      if (queued && !this.closed) {
        try {
          this.enter(() => {
            this.db
              .prepare("DELETE FROM waiters WHERE waiter_id=?")
              .run(waiterId);
          }, kind);
        } catch (error) {
          if (!sqliteBusy(error)) throw error;
        }
      }
    }
  }
  private pause(signal: AbortSignal | undefined, ms: number) {
    return new Promise<void>((resolve) => {
      const done = () => {
        clearTimeout(timer);
        signal?.removeEventListener("abort", done);
        resolve();
      };
      const timer = setTimeout(done, ms);
      signal?.addEventListener("abort", done, { once: true });
      if (signal?.aborted) done();
    });
  }
  private probeRuntime(runtimeId: string): "alive" | "dead" | "unknown" {
    this.assertHeld();
    if (runtimeId === this.runtimeId) return "alive";
    const row = this.db
      .prepare(
        "SELECT runtime_id,lease_name,status FROM runtimes WHERE runtime_id=?",
      )
      .get(runtimeId) as unknown as RuntimeRow | undefined;
    if (!row) return "unknown";
    if (this.scope.getStore()!.provenDead.has(runtimeId)) return "dead";
    if (
      row.lease_name !== `${runtimeId}.sqlite` ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(runtimeId)
    )
      return "unknown";
    const path = join(this.controlHome, "runtimes", row.lease_name);
    // Never create a missing lease while trying to prove another runtime dead.
    if (!existsSync(path)) return "unknown";
    let probe: DatabaseSync | undefined;
    try {
      probe = new DatabaseSync(path);
      configure(probe);
      probe.exec("BEGIN IMMEDIATE");
      const identity = probe.prepare("SELECT identity FROM lease").get() as
        | { identity: string }
        | undefined;
      if (identity?.identity !== runtimeId) return "unknown";
      this.scope.getStore()!.provenDead.add(runtimeId);
      this.scope.getStore()!.probes.push(probe);
      probe = undefined;
      this.db
        .prepare("UPDATE runtimes SET status='dead' WHERE runtime_id=?")
        .run(runtimeId);
      for (const pending of this.db
        .prepare(
          "SELECT json FROM operations WHERE runtime_id=? AND status='active'",
        )
        .all(runtimeId) as unknown as { json: string }[]) {
        const operation = JSON.parse(pending.json) as Operation;
        operation.status = "unknown";
        operation.updated_at = new Date().toISOString();
        this.save(operation);
      }
      return "dead";
    } catch (error) {
      if (sqliteBusy(error)) return "alive";
      return "unknown";
    } finally {
      probe?.close();
    }
  }
  runtimeStatus(runtimeId: string): "alive" | "dead" | "unknown" {
    return this.probeRuntime(runtimeId);
  }
  reserve(reservation: Reservation): Operation {
    this.assertHeld();
    assertReservation(reservation);
    if (this.maintenanceState().mode !== "normal")
      busy("New external operations are fenced while maintenance drains.");
    const existing = this.lookup(reservation.operation_id);
    const resources = [...new Set(reservation.resources)].sort();
    if (existing) {
      if (
        existing.runtime_id === this.runtimeId &&
        existing.status === "active" &&
        existing.epoch === reservation.epoch &&
        existing.kind === reservation.kind &&
        existing.digest === reservation.digest &&
        existing.session_id === reservation.session_id &&
        JSON.stringify(existing.metadata) ===
          JSON.stringify(reservation.metadata) &&
        JSON.stringify(existing.resources) === JSON.stringify(resources)
      )
        return existing;
      busy(
        "Operation identity is already reserved; explicit recovery is required.",
      );
    }
    for (const resource of resources) {
      if (
        this.db
          .prepare(
            "SELECT operation_id FROM resource_reservations WHERE resource=? LIMIT 1",
          )
          .get(resource)
      )
        busy("A requested resource is reserved by a pending operation.");
      if (
        this.db
          .prepare(
            "SELECT 1 FROM operations o,json_each(o.json,'$.resources') resource WHERE o.status='unknown' AND resource.value=? LIMIT 1",
          )
          .get(resource)
      )
        busy("A requested resource has an unresolved portable operation.");
    }
    const now = new Date().toISOString();
    const operation: Operation = {
      ...reservation,
      resources,
      runtime_id: this.runtimeId,
      phase: "reserved",
      status: "active",
      created_at: now,
      updated_at: now,
    };
    this.save(operation);
    for (const resource of resources)
      this.db
        .prepare(
          "INSERT INTO resource_reservations(resource,operation_id) VALUES(?,?)",
        )
        .run(resource, operation.operation_id);
    return operation;
  }
  operation(id: string) {
    this.assertHeld();
    return this.lookup(id);
  }
  pending(): Operation[] {
    this.assertHeld();
    return (
      this.db
        .prepare(
          "SELECT json FROM operations WHERE status<>'settled' ORDER BY operation_id",
        )
        .all() as unknown as { json: string }[]
    ).map((row) => JSON.parse(row.json) as Operation);
  }
  captureOperations(): { watermark: number; pending: Operation[] } {
    this.assertHeld();
    const row = this.db
      .prepare("SELECT coalesce(max(rowid),0) AS watermark FROM operations")
      .get() as { watermark: number };
    return { watermark: row.watermark, pending: this.pending() };
  }
  operationsSince(watermark: number): Operation[] {
    this.assertHeld();
    if (!Number.isSafeInteger(watermark) || watermark < 0)
      failure(
        "VALIDATION_ERROR",
        "An operation capture watermark must be a nonnegative safe integer.",
      );
    return (
      this.db
        .prepare("SELECT json FROM operations WHERE rowid>? ORDER BY rowid")
        .all(watermark) as unknown as { json: string }[]
    ).map((row) => JSON.parse(row.json) as Operation);
  }
  private owned(id: string): Operation {
    const operation = this.lookup(id);
    if (
      !operation ||
      operation.runtime_id !== this.runtimeId ||
      operation.status !== "active"
    )
      failure(
        "STORE_BUSY",
        "Operation has no live reservation owned by this runtime.",
      );
    return operation;
  }
  phase(id: string, phase: string): Operation {
    this.assertHeld();
    if (!phase || typeof phase !== "string")
      failure("VALIDATION_ERROR", "An operation phase is required.");
    const operation = this.owned(id);
    operation.phase = phase;
    operation.updated_at = new Date().toISOString();
    this.save(operation);
    return operation;
  }
  unknown(id: string): Operation {
    this.assertHeld();
    const operation = this.lookup(id);
    if (
      !operation ||
      operation.runtime_id !== this.runtimeId ||
      operation.status === "settled"
    )
      failure(
        "STORE_BUSY",
        "Only this runtime's unsettled operation can be marked unknown.",
      );
    operation.status = "unknown";
    operation.phase = "unknown";
    operation.updated_at = new Date().toISOString();
    this.save(operation);
    return operation;
  }
  release(id: string): void {
    this.assertHeld();
    const operation = this.owned(id);
    operation.status = "settled";
    operation.phase = "settled";
    operation.updated_at = new Date().toISOString();
    this.save(operation);
    this.db
      .prepare("DELETE FROM resource_reservations WHERE operation_id=?")
      .run(id);
  }
  adopt(id: string): Operation {
    this.assertHeld();
    const operation = this.lookup(id);
    if (!operation || operation.status === "settled")
      failure("VALIDATION_ERROR", "There is no pending operation to recover.");
    for (const resource of operation.resources) {
      const owner = this.db
        .prepare(
          "SELECT 1 FROM resource_reservations WHERE resource=? AND operation_id<>? LIMIT 1",
        )
        .get(resource, id);
      if (owner) busy("Recovery resource is still owned by another operation.");
      if (
        this.db
          .prepare(
            "SELECT 1 FROM operations o,json_each(o.json,'$.resources') r WHERE o.status='unknown' AND o.operation_id<>? AND r.value=? LIMIT 1",
          )
          .get(id, resource)
      )
        busy("Another unknown operation also pins this recovery resource.");
    }
    if (operation.runtime_id === this.runtimeId) {
      if (operation.status === "unknown") {
        operation.status = "active";
        operation.updated_at = new Date().toISOString();
        this.save(operation);
        return operation;
      }
      return this.owned(id);
    }
    if (this.probeRuntime(operation.runtime_id) !== "dead")
      busy(
        "The operation's runtime is alive or its OS lease cannot be proved dead.",
      );
    // Probe may have changed durable status to unknown; preserve all metadata.
    const adopted = this.lookup(id)!;
    adopted.runtime_id = this.runtimeId;
    adopted.status = "active";
    adopted.updated_at = new Date().toISOString();
    this.save(adopted);
    return adopted;
  }
  beginMaintenance(kind = "maintenance", expectedEpoch?: string): string {
    this.assertHeld();
    const state = this.maintenanceState();
    if (state.mode !== "normal") {
      if (state.runtime_id === this.runtimeId) return state.token!;
      // A dead administrator may have performed an irreversible filesystem
      // switch. Recovery must inspect this fence, never silently clear it.
      busy("Another runtime owns an unresolved maintenance fence.");
    }
    const token = randomUUID();
    this.db
      .prepare(
        "UPDATE maintenance SET mode='draining',runtime_id=?,token=?,kind=?,expected_epoch=? WHERE singleton=1",
      )
      .run(this.runtimeId, token, kind, expectedEpoch ?? null);
    return token;
  }
  /** Narrow crash-recovery entry; generic phase admission remains fenced. */
  adoptMaintenance(token: string): string {
    this.assertOpen();
    if (!this.held) {
      try {
        return this.enter(() => this.adoptMaintenance(token), "maintenance");
      } catch (error) {
        if (sqliteBusy(error))
          busy(
            "Another runtime holds the gate; retry maintenance adoption asynchronously.",
          );
        throw error;
      }
    }
    if (this.scope.getStore()!.kind !== "maintenance")
      failure(
        "VALIDATION_ERROR",
        "Maintenance recovery requires a maintenance capability.",
      );
    const state = this.maintenanceState();
    if (state.mode === "normal" || state.token !== token || !state.runtime_id)
      failure(
        "STORE_BUSY",
        "The exact unresolved maintenance token is required for recovery.",
      );
    if (state.runtime_id === this.runtimeId) return token;
    if (this.probeRuntime(state.runtime_id) !== "dead")
      busy("Maintenance owner is alive or its OS lease cannot be proved dead.");
    this.db
      .prepare("UPDATE maintenance SET runtime_id=? WHERE singleton=1")
      .run(this.runtimeId);
    return token;
  }
  private assertMaintenance(token?: string) {
    const state = this.maintenanceState();
    if (
      state.mode === "normal" ||
      state.runtime_id !== this.runtimeId ||
      (token !== undefined && state.token !== token)
    )
      failure("STORE_BUSY", "This runtime does not own the maintenance fence.");
    return state;
  }
  drainMaintenance(): { pending: number; operations: Operation[] } {
    this.assertHeld();
    this.assertMaintenance();
    for (const runtimeId of new Set(
      this.pending()
        .filter((operation) => operation.status === "active")
        .map((operation) => operation.runtime_id),
    )) {
      if (runtimeId !== this.runtimeId) this.probeRuntime(runtimeId);
    }
    const operations = this.pending();
    return {
      pending: operations.filter((operation) => operation.status === "active")
        .length,
      operations,
    };
  }
  exclusiveMaintenance(token?: string) {
    this.assertHeld();
    this.assertMaintenance(token);
    if (this.drainMaintenance().pending)
      busy(
        "Live external operations must settle before exclusive maintenance.",
      );
    this.db
      .prepare("UPDATE maintenance SET mode='exclusive' WHERE singleton=1")
      .run();
  }
  endMaintenance(token?: string) {
    this.assertHeld();
    this.assertMaintenance(token);
    this.db
      .prepare(
        "UPDATE maintenance SET mode='normal',runtime_id=NULL,token=NULL,kind=NULL,expected_epoch=NULL WHERE singleton=1",
      )
      .run();
  }
  /** Repair the file-marker/coordination-COMMIT gap. Never alters an existing
   * live/settled operation. Unknown collision rows remain resource barriers. */
  importMissingUnknown(operations: readonly Operation[]) {
    this.assertHeld();
    for (const source of operations) {
      assertReservation(source);
      if (source.status === "settled" || this.lookup(source.operation_id))
        continue;
      if (!/^[A-Za-z0-9_-]{1,128}$/.test(source.runtime_id))
        failure("VALIDATION_ERROR", "Invalid portable runtime identity.");
      const operation: Operation = {
        ...source,
        resources: [...new Set(source.resources)].sort(),
        status: "unknown",
        phase: "unknown",
      };
      this.save(operation);
      this.db
        .prepare(
          "INSERT OR IGNORE INTO runtimes(runtime_id,lease_name,status,created_at) VALUES(?,?,'unknown',?)",
        )
        .run(
          source.runtime_id,
          source.runtime_id + ".sqlite",
          source.created_at,
        );
      for (const resource of operation.resources)
        this.db
          .prepare("INSERT OR IGNORE INTO resource_reservations VALUES(?,?)")
          .run(resource, operation.operation_id);
    }
  }
  importUnknown(operations: readonly Operation[]) {
    this.assertHeld();
    if (this.assertMaintenance().mode !== "exclusive")
      failure(
        "STORE_BUSY",
        "Importing recovery barriers requires exclusive maintenance.",
      );
    for (const source of operations) {
      assertReservation(source);
      if (source.status === "settled") continue;
      if (!/^[A-Za-z0-9_-]{1,128}$/.test(source.runtime_id))
        failure("VALIDATION_ERROR", "Invalid imported runtime identity.");
      const existing = this.lookup(source.operation_id);
      const resources = [
        ...new Set([...(existing?.resources ?? []), ...source.resources]),
      ].sort();
      const operation: Operation =
        existing && existing.status !== "settled"
          ? { ...existing, resources }
          : { ...source, resources, status: "unknown" };
      if (!existing || existing.status === "settled")
        operation.status = "unknown";
      this.save(operation);
      this.db
        .prepare(
          "INSERT OR IGNORE INTO runtimes(runtime_id,lease_name,status,created_at) VALUES(?,?,'unknown',?)",
        )
        .run(
          source.runtime_id,
          `${source.runtime_id}.sqlite`,
          source.created_at,
        );
      for (const resource of resources)
        this.db
          .prepare(
            "INSERT OR IGNORE INTO resource_reservations(resource,operation_id) VALUES(?,?)",
          )
          .run(resource, source.operation_id);
    }
  }
  describe() {
    return {
      identity: this.identity,
      runtime_id: this.runtimeId,
      mode: "sqlite-delete-global-phase" as const,
      closed: this.closed,
      waiting: this.waiting,
      ...this.stats,
    };
  }
  close(options: { poisonUnknown?: boolean } = {}) {
    if (this.closed) return;
    if (this.transaction || this.waiting)
      busy(
        "Drain admitted callbacks and queued requests before closing their runtime lease.",
      );
    try {
      this.enter(() => {
        const own = this.pending().filter(
          (operation) => operation.runtime_id === this.runtimeId,
        );
        if (own.length && !options.poisonUnknown)
          busy(
            "This runtime still owns unsettled operations; settle or explicitly poison them before close.",
          );
        if (this.maintenanceState().runtime_id === this.runtimeId)
          busy("This runtime still owns an unresolved maintenance fence.");
        for (const operation of own) {
          operation.status = "unknown";
          operation.updated_at = new Date().toISOString();
          this.save(operation);
        }
        this.db
          .prepare("DELETE FROM waiters WHERE runtime_id=?")
          .run(this.runtimeId);
        this.db
          .prepare("UPDATE runtimes SET status='dead' WHERE runtime_id=?")
          .run(this.runtimeId);
      }, "maintenance");
    } catch (error) {
      if (sqliteBusy(error))
        busy(
          "Another runtime holds the gate; retry close after callbacks drain.",
        );
      throw error;
    }
    this.db.close();
    // Release the OS lifetime lease only after no callback can use this runtime.
    this.lease.exec("ROLLBACK");
    this.lease.close();
    this.closed = true;
    this.scope.disable();
  }
}
