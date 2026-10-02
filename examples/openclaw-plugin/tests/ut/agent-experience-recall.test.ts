import { describe, expect, it } from "vitest";

import { shouldRecallAgentExperience } from "../../auto-recall.js";

describe("shouldRecallAgentExperience", () => {
  it("skips ordinary knowledge questions", () => {
    const result = shouldRecallAgentExperience({
      latestUserText: "preflight assemble 和 transformcontext assemble是什麼區別",
    });
    expect(result.recall).toBe(false);
  });

  it("recalls for execution tasks", () => {
    const result = shouldRecallAgentExperience({
      latestUserText: "修一下 OpenClaw 外掛裡 afterTurn 寫入 tool result 的問題",
    });
    expect(result.recall).toBe(true);
    expect(result.reason).toBe("task_execution");
  });

  it("forces recall for cron sessions", () => {
    const result = shouldRecallAgentExperience({
      latestUserText: "每天同步 benchmark 結果並生成報告",
      sessionKey: "agent:main:cron:nightly:run:1",
      triggerHint: "cron_start",
    });
    expect(result.recall).toBe(true);
    expect(result.reason).toBe("forced_trigger");
    expect(result.trigger).toBe("cron_start");
  });
});
