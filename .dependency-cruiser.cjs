module.exports = {
  forbidden: [
    { name: "no-cycles", severity: "error", from: {}, to: { circular: true } },
    {
      name: "portable-core",
      severity: "error",
      from: { path: "^src/core" },
      to: {
        path: "^src/(extension|storage)|node_modules/@earendil-works|node_modules/typebox",
      },
    },
    {
      name: "storage-has-no-pi",
      severity: "error",
      from: { path: "^src/storage" },
      to: {
        path: "^src/extension|node_modules/@earendil-works|node_modules/typebox",
      },
    },
    {
      name: "public-module-api",
      severity: "error",
      from: { path: "^src/extension" },
      to: { path: "^src/(core|storage)/", pathNot: "/index\\.ts$" },
    },
  ],
  options: {
    tsConfig: { fileName: "tsconfig.json" },
    doNotFollow: { path: "node_modules" },
  },
};
