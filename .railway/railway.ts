import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

// This file owns only the gate service and its log volume. An apply does not
// delete other resources in the same Railway project.
export const partial = "argentine-a2a";

export default defineRailway(() => {
  const gateLog = volume("argentine_gate_log", {
    sizeMB: 1024,
  });

  const gate = service("argentine-a2a", {
    source: github("dlescanogithub/argentine-a2a", { branch: "main" }),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
    },
    healthcheck: "/health",
    healthcheckTimeout: 30,
    replicas: 1,
    deploy: {
      requiredMountPath: "/data",
    },
    volumeMounts: {
      "/data": gateLog,
    },
    env: {
      ARGENTINE_BIND: "0.0.0.0",
      ARGENTINE_REQUIRE_ALLOWLIST_SECRET: "1",
      ARGENTINE_LOG_PATH: "/data/gate-log.jsonl",
      ARGENTINE_DIEGO_OFF_FILE: "/data/diego.off",
      ARGENTINE_STDOUT_LOG: "1",
      ARGENTINE_LOG_MAX_BYTES: "5242880",
      ARGENTINE_LOG_BACKUPS: "3",
      // Keep dashboard values. This file has no token and no off-switch state.
      ARGENTINE_ALLOWLIST: preserve(),
      ARGENTINE_DIEGO_OFF: preserve(),
    },
  });

  return project("argentine-a2a", {
    resources: [gate, gateLog],
  });
});
