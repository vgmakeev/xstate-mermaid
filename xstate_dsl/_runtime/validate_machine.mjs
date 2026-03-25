/**
 * XState v5 runtime validation script.
 * Reads JSON from stdin, creates machine + actor, optionally runs scenarios.
 * Outputs structured JSON to stdout.
 */
import { createMachine, createActor, fromPromise } from "xstate";

const input = await readStdin();
let payload;

try {
  payload = JSON.parse(input);
} catch {
  output({ valid: false, errors: ["Invalid JSON input"] });
  process.exit(0);
}

const { config: entry, scenarios } = payload;
const result = { valid: false, errors: [], warnings: [], initialState: null, scenarios: [] };

// Phase 1: Create machine + actor
try {
  const machine = buildMachine(entry);
  const actor = createActor(machine);
  actor.start();

  const snap = actor.getSnapshot();
  result.valid = true;
  result.initialState = snap.value;

  // Phase 2: Run scenarios if provided
  if (scenarios && scenarios.length > 0) {
    result.scenarios = runScenarios(machine, scenarios);
  }

  actor.stop();
} catch (e) {
  result.errors.push(`createMachine/createActor failed: ${e.message}`);
}

output(result);

// ─── Helpers ────────────────────────────────────────────────────

function buildMachine(entry) {
  const { setup: setupDef = {}, config } = entry;

  const implementations = {
    actions: {},
    guards: {},
    actors: {},
  };

  if (setupDef.actions) {
    for (const name of Object.keys(setupDef.actions)) {
      implementations.actions[name] = () => {};
    }
  }

  if (setupDef.guards) {
    for (const name of Object.keys(setupDef.guards)) {
      implementations.guards[name] = () => true;
    }
  }

  if (setupDef.actors) {
    for (const name of Object.keys(setupDef.actors)) {
      implementations.actors[name] = fromPromise(() => new Promise(() => {}));
    }
  }

  // Handle string context (raw expressions) → empty object
  const context =
    typeof config.context === "string" ? {} : config.context || {};

  return createMachine({ ...config, context }, implementations);
}

function runScenarios(machine, scenarios) {
  const results = [];

  for (let i = 0; i < scenarios.length; i++) {
    const scenario = scenarios[i];
    const steps = scenario.steps || (Array.isArray(scenario) ? scenario : [scenario]);
    const actor = createActor(machine);
    actor.start();

    // Check initial state if specified
    if (scenario.initial) {
      const snap = actor.getSnapshot();
      const actual = formatValue(snap.value);
      const expected = scenario.initial;
      results.push({
        scenario: i,
        step: 0,
        type: "initial",
        expected,
        actual,
        pass: matches(snap.value, expected),
      });
    }

    for (let j = 0; j < steps.length; j++) {
      const step = steps[j];
      try {
        actor.send({ type: step.send });
        const snap = actor.getSnapshot();
        const actual = formatValue(snap.value);
        const expected = step.expect;
        results.push({
          scenario: i,
          step: j + 1,
          type: "transition",
          send: step.send,
          expected,
          actual,
          pass: matches(snap.value, expected),
          status: snap.status,
        });
      } catch (e) {
        results.push({
          scenario: i,
          step: j + 1,
          type: "transition",
          send: step.send,
          expected: step.expect,
          actual: null,
          pass: false,
          error: e.message,
        });
      }
    }

    try { actor.stop(); } catch {}
  }

  return results;
}

function matches(actual, expected) {
  if (typeof expected === "string") {
    if (typeof actual === "string") return actual === expected;
    // Support dot notation for nested: "parent.child"
    const parts = expected.split(".");
    let val = actual;
    for (const part of parts) {
      if (val && typeof val === "object" && part in val) {
        val = val[part];
      } else {
        return false;
      }
    }
    return typeof val === "string";
  }
  // Deep object comparison for parallel states
  return JSON.stringify(actual) === JSON.stringify(expected);
}

function formatValue(val) {
  if (typeof val === "string") return val;
  return val;
}

function output(data) {
  process.stdout.write(JSON.stringify(data));
}

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
  });
}
