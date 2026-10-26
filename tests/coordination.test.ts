import test from "node:test";
import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { Coordination, type Operation } from "../src/storage/coordination.ts";

const delay = (ms: number) => new Promise<void>((done) => setTimeout(done, ms));
const fixture = () =>
  mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-coordination-"),
  );
const isCode = (code: string) => (error: unknown) =>
  (error as { code?: string }).code === code;
function reservation(id: string, resources: string[] = ["document:a"]) {
  return {
    operation_id: id,
    epoch: "epoch",
    kind: "document",
    digest: "digest",
    resources,
    metadata: { effect: { expected: "original" } },
  };
}
async function until(predicate: () => boolean, timeout = 10_000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) {
    if (Date.now() > deadline)
      assert.fail("Timed out waiting for child fixture progress");
    await delay(10);
  }
}
const moduleUrl = pathToFileURL(resolve("src/storage/coordination.ts")).href;
function child(
  home: string,
  identity: string,
  action: "reserve" | "hold" | "queue" | "maintenance",
  name: string,
) {
  const script = `
    import { Coordination } from ${JSON.stringify(moduleUrl)};
    import { appendFileSync, existsSync, writeFileSync } from 'node:fs';
    import { join } from 'node:path';
    const home = ${JSON.stringify(home)}, action = ${JSON.stringify(action)}, name = ${JSON.stringify(name)};
    let c;
    for (;;) {
      try { c = new Coordination(home, undefined, {expectedId:${JSON.stringify(identity)},create:false}); break; }
      catch (e) { if(e.code!=='STORE_BUSY') throw e; await new Promise(r=>setTimeout(r,10)); }
    }
    async function close() {
      for (;;) { try { c.close(); break; } catch(e) { if(e.code!=='STORE_BUSY' && !/database is locked/.test(e.message)) throw e; await new Promise(r=>setTimeout(r,10)); } }
      process.disconnect();
    }
    if (action === 'maintenance') {
      const token = c.sync('maintenance',()=>c.beginMaintenance('restore','epoch'));
      process.send({type:'ready',runtime:c.runtimeId,token});
      setInterval(()=>{},1000);
    } else if (action === 'reserve') {
      c.sync('mutate',()=>c.reserve({operation_id:'native-operation',epoch:'epoch',kind:'document',digest:'digest',resources:['document:a']}));
      process.send({type:'ready',runtime:c.runtimeId});
      setInterval(()=>{},1000);
    } else if (action === 'hold') {
      process.send({type:'ready',runtime:c.runtimeId});
      process.on('message', async message => {
        if(message !== 'start') return;
        c.sync('mutate',()=>{
          writeFileSync(join(home,'held'), 'held');
          const cell=new Int32Array(new SharedArrayBuffer(4));
          while(!existsSync(join(home,'release'))) Atomics.wait(cell,0,0,10);
        });
        process.send({type:'done'});
        await close();
      });
    } else {
      process.send({type:'ready',runtime:c.runtimeId});
      process.on('message', async message => {
        if(message !== 'start') return;
        await c.run('mutate',()=>appendFileSync(join(home,'order'), name+'\\n'),{timeoutMs:10000});
        process.send({type:'done'});
        await close();
      });
    }
  `;
  const proc = spawn(
    process.execPath,
    ["--import", "tsx", "--input-type=module", "-e", script],
    { cwd: resolve("."), stdio: ["ignore", "pipe", "pipe", "ipc"] },
  );
  let stderr = "";
  proc.stderr!.on("data", (chunk) => {
    stderr += String(chunk);
  });
  const messages: { type: string; runtime?: string; token?: string }[] = [];
  proc.on("message", (message) => {
    messages.push(
      message as { type: string; runtime?: string; token?: string },
    );
  });
  return { proc, messages, error: () => stderr };
}
async function stop(proc: ChildProcess) {
  if (proc.exitCode !== null || proc.signalCode !== null) return;
  const exit = once(proc, "exit");
  proc.kill();
  await exit;
}

// Synthetic process tests deliberately preserve their temporary SQLite files for
// diagnosis. They never inspect owner data or contact models/providers.
test("coordination keeps stable identity, rejects async phases and revokes detached capabilities", async () => {
  const home = fixture(),
    c = new Coordination(home);
  assert.throws(() => c.assertHeld(), isCode("STORE_BUSY"));
  let detached: Promise<void> | undefined;
  let token: object | undefined;
  assert.equal(
    c.sync("read", () => {
      c.assertHeld();
      token = c.phaseToken;
      assert.equal(Object.isFrozen(token), true);
      assert.equal(
        c.sync("read", () => c.phaseToken),
        token,
      );
      detached = Promise.resolve().then(() => {
        assert.equal(c.held, false);
        assert.throws(() => c.sync("read", () => 1), isCode("STORE_BUSY"));
      });
      assert.throws(
        () => c.sync("mutate", () => 1),
        isCode("VALIDATION_ERROR"),
      );
      return c.sync("read", () => 42);
    }),
    42,
  );
  await detached;
  assert.equal(c.phaseToken, undefined);
  assert.notEqual(
    c.sync("read", () => c.phaseToken),
    token,
  );
  assert.throws(
    () =>
      c.sync("read", async () => {
        await delay(1);
        assert.throws(() => c.assertHeld(), isCode("STORE_BUSY"));
      }),
    isCode("VALIDATION_ERROR"),
  );
  await delay(5);
  const identity = c.identity;
  c.close();
  const reopened = new Coordination(home, undefined, {
    expectedId: identity,
    create: false,
  });
  assert.equal(reopened.identity, identity);
  reopened.close();
  assert.throws(
    () =>
      new Coordination(home, undefined, {
        expectedId: "foreign",
        create: false,
      }),
    isCode("STORE_UNAVAILABLE"),
  );
  const missing = join(fixture(), "missing");
  assert.throws(
    () =>
      new Coordination(missing, undefined, {
        expectedId: identity,
        create: false,
      }),
    isCode("STORE_UNAVAILABLE"),
  );
  assert.equal(existsSync(join(missing, "coordination.sqlite")), false);
});

test("resource reservations are atomic, durable, narrow and retain settled history", () => {
  const home = fixture(),
    a = new Coordination(home),
    b = new Coordination(home);
  a.sync("mutate", () => a.reserve(reservation("a", ["a"])));
  assert.throws(
    () => b.sync("mutate", () => b.reserve(reservation("b", ["b", "a"]))),
    isCode("STORE_BUSY"),
  );
  a.sync("settle", () => a.release("a"), { operationId: "a" });
  b.sync("mutate", () => b.reserve(reservation("b", ["b"])));
  assert.throws(() => b.close(), isCode("STORE_BUSY"));
  b.sync("settle", () => b.release("b"), { operationId: "b" });
  assert.equal(a.sync("read", () => a.operation("a"))?.status, "settled");
  assert.deepEqual(a.sync("read", () => a.operation("a"))?.metadata, {
    effect: { expected: "original" },
  });
  assert.deepEqual(
    a.sync("read", () => a.pending()),
    [],
  );
  a.close();
  b.close();
});

test(
  "a paused live runtime cannot be reclaimed; only death of its SQLite lease permits explicit adoption",
  { timeout: 20_000 },
  async (t) => {
    const home = fixture(),
      c = new Coordination(home),
      owner = child(home, c.identity, "reserve", "owner");
    t.after(async () => {
      await stop(owner.proc);
    });
    await until(() => owner.messages.some((m) => m.type === "ready"));
    const foreign = owner.messages.find((m) => m.type === "ready")!.runtime!;
    await delay(60);
    assert.throws(
      () => c.sync("mutate", () => c.adopt("native-operation")),
      isCode("STORE_BUSY"),
    );
    assert.throws(
      () => c.sync("mutate", () => c.reserve(reservation("competing"))),
      isCode("STORE_BUSY"),
    );
    assert.equal(
      c.sync("read", () => c.operation("native-operation"))?.runtime_id,
      foreign,
    );
    await stop(owner.proc);
    const adopted = c.sync("settle", () => c.adopt("native-operation"));
    assert.equal(adopted.runtime_id, c.runtimeId);
    assert.equal(adopted.status, "active");
    assert.equal(existsSync(join(home, "runtimes", `${foreign}.sqlite`)), true);
    c.sync("settle", () => c.release("native-operation"), {
      operationId: "native-operation",
    });
    c.close();
  },
);

test(
  "a real foreign gate is fail-fast for sync calls and async waiting remains cancellable and bounded",
  { timeout: 20_000 },
  async (t) => {
    const home = fixture(),
      c = new Coordination(home),
      owner = child(home, c.identity, "hold", "owner");
    t.after(async () => {
      if (!existsSync(join(home, "release")))
        writeFileSync(join(home, "release"), "release");
      await stop(owner.proc);
    });
    await until(() => owner.messages.some((m) => m.type === "ready"));
    owner.proc.send("start");
    await until(() => existsSync(join(home, "held")));
    const start = performance.now();
    assert.throws(() => c.sync("read", () => 1), isCode("STORE_BUSY"));
    assert.ok(performance.now() - start < 250);
    let invoked = false;
    const controller = new AbortController();
    const waiting = c.run(
      "read",
      () => {
        invoked = true;
      },
      { signal: controller.signal },
    );
    await delay(25);
    controller.abort();
    await assert.rejects(waiting, isCode("STORE_CANCELLED"));
    await assert.rejects(
      c.run(
        "read",
        () => {
          invoked = true;
        },
        { timeoutMs: 30 },
      ),
      isCode("STORE_BUSY"),
    );
    assert.equal(invoked, false);
    writeFileSync(join(home, "release"), "release");
    await once(owner.proc, "exit");
    assert.equal(owner.proc.exitCode, 0, owner.error());
    assert.equal(await c.run("read", () => 7), 7);
    c.close();
  },
);

test(
  "two process waiters enter in durable FIFO order after a maintenance drain fence",
  { timeout: 20_000 },
  async (t) => {
    const home = fixture(),
      c = new Coordination(home);
    const one = child(home, c.identity, "queue", "one"),
      two = child(home, c.identity, "queue", "two");
    t.after(async () => {
      await Promise.all([stop(one.proc), stop(two.proc)]);
    });
    await until(
      () =>
        one.messages.some((m) => m.type === "ready") &&
        two.messages.some((m) => m.type === "ready"),
    );
    const token = c.sync("maintenance", () => c.beginMaintenance("test"));
    const observer = new DatabaseSync(join(home, "coordination.sqlite"), {
      readOnly: true,
    });
    observer.exec("PRAGMA busy_timeout=0");
    const queued = () =>
      (
        observer.prepare("SELECT count(*) AS n FROM waiters").get() as {
          n: number;
        }
      ).n;
    one.proc.send("start");
    await until(() => queued() === 1);
    two.proc.send("start");
    await until(() => {
      assert.equal(two.proc.exitCode, null, two.error());
      return queued() === 2;
    });
    observer.close();
    await c.run("maintenance", () => c.endMaintenance(token));
    await Promise.all([once(one.proc, "exit"), once(two.proc, "exit")]);
    assert.equal(one.proc.exitCode, 0, one.error());
    assert.equal(two.proc.exitCode, 0, two.error());
    assert.equal(readFileSync(join(home, "order"), "utf8"), "one\ntwo\n");
    c.close();
  },
);

test("draining admits owned settlers, exclusive fences readers, unknown barriers survive a switch", async () => {
  const home = fixture(),
    a = new Coordination(home),
    b = new Coordination(home);
  b.sync("mutate", () => b.reserve(reservation("live")));
  const token = a.sync("maintenance", () =>
    a.beginMaintenance("restore", "epoch"),
  );
  assert.equal(a.sync("maintenance", () => a.drainMaintenance()).pending, 1);
  assert.throws(
    () => a.sync("maintenance", () => a.exclusiveMaintenance(token)),
    isCode("STORE_BUSY"),
  );
  await assert.rejects(
    b.run("mutate", () => b.reserve(reservation("new")), { timeoutMs: 25 }),
    isCode("STORE_BUSY"),
  );
  b.sync("settle", () => b.release("live"), { operationId: "live" });
  a.sync("maintenance", () => {
    a.exclusiveMaintenance(token);
    const source: Operation = {
      ...reservation("old", ["document:old"]),
      runtime_id: "absent-old-runtime",
      phase: "dispatched",
      status: "active",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    a.importUnknown([source]);
    assert.equal(a.drainMaintenance().pending, 0);
    assert.equal(a.pending()[0].status, "unknown");
  });
  assert.throws(() => b.sync("read", () => 1), isCode("STORE_BUSY"));
  a.sync("maintenance", () => a.endMaintenance(token));
  assert.throws(
    () =>
      b.sync("mutate", () =>
        b.reserve(reservation("collision", ["document:old"])),
      ),
    isCode("STORE_BUSY"),
  );
  assert.throws(
    () => b.sync("settle", () => b.adopt("old")),
    isCode("STORE_BUSY"),
  );
  b.sync("mutate", () =>
    b.reserve(reservation("independent", ["document:new"])),
  );
  b.sync("settle", () => b.release("independent"), {
    operationId: "independent",
  });
  a.close();
  b.close();
});

test("explicit unknown shutdown releases only its own lease and keeps durable resource barriers", () => {
  const home = fixture(),
    a = new Coordination(home),
    b = new Coordination(home);
  a.sync("mutate", () => a.reserve(reservation("lost-reply")));
  assert.throws(
    () => a.sync("mutate", () => a.close({ poisonUnknown: true })),
    isCode("STORE_BUSY"),
  );
  a.close({ poisonUnknown: true });
  assert.equal(
    b.sync("read", () => b.operation("lost-reply"))?.status,
    "unknown",
  );
  assert.throws(
    () => b.sync("mutate", () => b.reserve(reservation("collision"))),
    isCode("STORE_BUSY"),
  );
  b.sync("settle", () => {
    b.adopt("lost-reply");
    b.release("lost-reply");
  });
  b.close();
});

test("cancelled FIFO tickets expire before admission even when cancellation cleanup encounters a foreign gate", async () => {
  const home = fixture(),
    c = new Coordination(home),
    follower = new Coordination(home);
  const token = c.sync("maintenance", () => c.beginMaintenance());
  const controller = new AbortController();
  let invoked = false;
  const waiting = follower.run(
    "mutate",
    () => {
      invoked = true;
    },
    { signal: controller.signal, timeoutMs: 30_000 },
  );
  const blocker = new DatabaseSync(join(home, "coordination.sqlite"));
  blocker.exec("PRAGMA busy_timeout=0");
  blocker.exec("BEGIN IMMEDIATE");
  controller.abort();
  await assert.rejects(waiting, isCode("STORE_CANCELLED"));
  blocker.exec("ROLLBACK");
  blocker.close();
  c.sync("maintenance", () => c.endMaintenance(token));
  const start = performance.now();
  assert.equal(await c.run("mutate", () => 7, { timeoutMs: 2500 }), 7);
  assert.ok(performance.now() - start < 2000);
  assert.equal(invoked, false);
  c.close();
  follower.close();
});

test(
  "maintenance recovery requires the exact fence token and proven death of its owner",
  { timeout: 20_000 },
  async (t) => {
    const home = fixture(),
      c = new Coordination(home),
      owner = child(home, c.identity, "maintenance", "administrator");
    t.after(async () => {
      await stop(owner.proc);
    });
    await until(() =>
      owner.messages.some((message) => message.type === "ready"),
    );
    const token = owner.messages.find(
      (message) => message.type === "ready",
    )!.token!;
    assert.throws(() => c.adoptMaintenance(token), isCode("STORE_BUSY"));
    await stop(owner.proc);
    assert.throws(
      () => c.adoptMaintenance("wrong-token"),
      isCode("STORE_BUSY"),
    );
    assert.equal(c.adoptMaintenance(token), token);
    c.sync("maintenance", () => {
      c.exclusiveMaintenance(token);
      c.endMaintenance(token);
    });
    c.close();
  },
);

test("operation capture includes fully settled operations created between backup snapshots", () => {
  const home = fixture(),
    c = new Coordination(home);
  c.sync("mutate", () => c.reserve(reservation("before", ["before"])));
  const capture = c.sync("read", () => c.captureOperations());
  assert.equal(capture.pending[0].operation_id, "before");
  c.sync("settle", () => c.release("before"));
  c.sync("mutate", () => {
    c.reserve(reservation("during", ["during"]));
    c.release("during");
  });
  const during = c.sync("read", () => c.operationsSince(capture.watermark));
  assert.equal(during.length, 1);
  assert.equal(during[0].operation_id, "during");
  assert.equal(during[0].status, "settled");
  assert.deepEqual(capture.pending[0].status, "active");
  assert.throws(
    () => c.sync("mutate", () => c.reserve(reservation("during", ["during"]))),
    isCode("STORE_BUSY"),
  );
  c.close();
});

test("SQLite BUSY after callback admission never redispatches that callback", async () => {
  const c = new Coordination(fixture());
  let calls = 0;
  const sqliteError = Object.assign(new Error("database is locked"), {
    errcode: 5,
  });
  await assert.rejects(
    c.run(
      "mutate",
      () => {
        calls++;
        throw sqliteError;
      },
      { timeoutMs: 100 },
    ),
    isCode("STORE_BUSY"),
  );
  assert.equal(calls, 1);
  c.close();
});

test("completed callback uncertainty retains barriers, allows own recovery, and never grants live foreign recovery", async () => {
  const home = fixture(),
    a = new Coordination(home),
    b = new Coordination(home);
  b.sync("mutate", () => {
    b.reserve(reservation("uncertain"));
    b.unknown("uncertain");
  });
  assert.equal(
    a.sync("read", () => a.runtimeStatus(b.runtimeId)),
    "alive",
  );
  assert.throws(
    () => a.sync("settle", () => a.adopt("uncertain")),
    isCode("STORE_BUSY"),
  );
  const token = a.sync("maintenance", () => a.beginMaintenance());
  assert.equal(a.sync("maintenance", () => a.drainMaintenance()).pending, 0);
  await b.run(
    "settle",
    () => {
      assert.equal(b.adopt("uncertain").status, "active");
      b.release("uncertain");
    },
    { operationId: "uncertain" },
  );
  a.sync("maintenance", () => a.endMaintenance(token));
  a.close();
  b.close();
});
