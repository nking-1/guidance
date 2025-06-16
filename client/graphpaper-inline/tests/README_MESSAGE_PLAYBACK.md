# Message Playback Testing

This document describes the new message recording and playback testing system for the guidance widget.

## Overview

The message playback system allows you to:
1. **Record** real guidance executions using the debug API
2. **Save** message streams as test fixtures
3. **Playback** recorded messages in tests to verify widget behavior
4. **Debug** complex scenarios with actual data

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Guidance Code   │────▶│ Debug Recording │────▶│ JSON Fixture    │
│ (Python)        │     │ System          │     │ File            │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Test Assertion  │◀────│ Widget Render   │◀────│ Message Playback│
│ (Playwright)    │     │                 │     │ (Test Harness)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Recording Test Scenarios

### Method 1: Manual Recording in Jupyter

```python
import guidance

# Enable debug recording
guidance.enable_widget_debug()
guidance.clear_widget_debug()

# Run your guidance code
from guidance import models, system, user, assistant, gen

gpt35 = models.OpenAI("gpt-3.5-turbo")

with system():
    lm = gpt35 + "You are a helpful assistant."

with user():
    lm += "What is the meaning of life?"

with assistant():
    lm += gen("response", max_tokens=10)

# Save the recording
debug_data = guidance.dump_widget_debug()
with open('tests/fixtures/my_test_scenario.json', 'w') as f:
    f.write(debug_data)
```

### Method 2: Using the Test Recorder Script

```bash
# List available scenarios
python scripts/record_widget_test.py --list

# Record a predefined scenario
python scripts/record_widget_test.py --name "role_test" --scenario multi_turn

# Output saved to: tests/fixtures/role_test_20250613_151230.json
```

## Writing Playback Tests

### Basic Playback Test

```javascript
const { test, expect } = require('@playwright/test');

test('should display recorded conversation correctly', async ({ page }) => {
  // Load test harness
  await page.goto('file://path/to/enhanced-test-harness.html');
  
  // Load recording
  const recording = require('../fixtures/role_test.json');
  
  // Playback messages
  await page.evaluate(async (rec) => {
    return window.testAPI.playbackMessages(rec, { delay: 50 });
  }, recording);
  
  // Assert widget state
  const roles = page.locator('.role-label');
  await expect(roles).toHaveCount(3); // system, user, assistant
});
```

### Testing Complex Scenarios

```javascript
test('should handle backtracking correctly', async ({ page }) => {
  const recording = require('../fixtures/backtrack_scenario.json');
  
  await page.evaluate(async (rec) => {
    return window.testAPI.playbackMessages(rec);
  }, recording);
  
  // Verify final state after backtracking
  const tokens = await page.locator('.token-grid-item').allTextContents();
  expect(tokens).not.toContain('wrong_answer');
  expect(tokens).toContain('correct_answer');
});
```

## Message Format

Recorded messages follow this structure:

```json
{
  "timestamp": "2025-06-13T15:30:00.123456",
  "messageCount": 42,
  "scenario_name": "multi_turn_conversation",
  "recorded_at": "2025-06-13T15:30:00.123456",
  "messages": [
    {
      "message_id": 1,
      "class_name": "ExecutionStartedMessage"
    },
    {
      "message_id": 2,
      "class_name": "TraceMessage",
      "trace_id": 1,
      "parent_trace_id": null,
      "node_attr": {
        "name": "user",
        "class_name": "RoleOpenerInput"
      }
    },
    {
      "message_id": 3,
      "class_name": "TraceMessage",
      "trace_id": 2,
      "parent_trace_id": 1,
      "node_attr": {
        "value": "Hello!",
        "is_input": true,
        "is_generated": false,
        "class_name": "TextOutput"
      }
    }
  ]
}
```

## Test Utilities

### Message Playback API

```javascript
// Play back all messages
await window.testAPI.playbackMessages(recording, {
  delay: 50,           // Delay between messages (ms)
  skipNonVisual: false // Skip non-rendering messages
});

// Get widget state after playback
const state = window.testAPI.getWidgetState();
// Returns: { tokens: [...], roles: [...], messageLog: [...] }
```

### TypeScript Helpers

```typescript
import { createTestScenario } from '../test-utils/message-playback';

const scenario = createTestScenario('my_test', recording);

// Helper methods
scenario.getRoleSequence();  // ['system', 'user', 'assistant']
scenario.getTokenCount();    // 42
scenario.findMessagesByType('RoleOpenerInput');
```

## Best Practices

1. **Record Real Scenarios**: Use actual guidance executions for authentic test data
2. **Name Descriptively**: Use clear names that describe what the test verifies
3. **Keep Recordings Small**: Focus on specific behaviors to test
4. **Version Control**: Commit fixture files for regression testing
5. **Document Edge Cases**: Add comments explaining what each recording tests

## Debugging

### View Message Flow

```javascript
// Enable message logging in test
await page.evaluate(() => {
  window.testAPI.messageLog.forEach(entry => {
    console.log(`${entry.source}: ${entry.message.class_name}`);
  });
});
```

### Inspect Widget State

```javascript
// During test execution
await page.pause(); // Playwright inspector
const state = await page.evaluate(() => window.testAPI.getWidgetState());
console.log('Current state:', state);
```

### Save Screenshots

```javascript
await page.screenshot({ path: 'debug-state.png' });
```

## Integration with CI/CD

```yaml
# .github/workflows/widget-tests.yml
- name: Run Widget Playback Tests
  run: |
    npm test tests/real-message-playback.spec.js
    
- name: Upload Test Recordings
  uses: actions/upload-artifact@v3
  with:
    name: test-recordings
    path: tests/fixtures/*.json
```

## Future Enhancements

1. **Visual Regression**: Screenshot comparison of rendered states
2. **Performance Metrics**: Track rendering time for large message streams  
3. **Fuzzing**: Generate random message sequences to find edge cases
4. **Cross-Browser**: Ensure consistent behavior across browsers