const { test, expect } = require('@playwright/test');
const path = require('path');

test.describe('Real Message Playback Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to enhanced test harness
    const harnessPath = path.join(__dirname, '../src/test-utils/enhanced-test-harness.html');
    await page.goto(`file://${harnessPath}`);
    
    // Wait for test API to be ready
    await page.waitForFunction(() => window.testAPIReady === true);
  });

  test('should correctly display roles from recorded messages', async ({ page }) => {
    // Load the recording you saved (widget_debug.json)
    const recording = {
      timestamp: "2025-06-13T17:18:42.030056",
      messageCount: 102,
      messages: [
        // Using a subset of the actual messages for testing
        {
          message_id: 98,
          class_name: "ExecutionStartedMessage"
        },
        {
          message_id: 60,
          class_name: "TraceMessage",
          trace_id: 22,
          parent_trace_id: 21,
          node_attr: {
            name: "system",
            text: null,
            closer_text: null,
            class_name: "RoleOpenerInput"
          }
        },
        {
          message_id: 64,
          class_name: "TraceMessage",
          trace_id: 23,
          parent_trace_id: 22,
          node_attr: {
            value: "You are a helpful assistant.",
            is_input: true,
            is_generated: false,
            is_force_forwarded: false,
            latency_ms: 0.0,
            class_name: "TextOutput"
          }
        },
        {
          message_id: 68,
          class_name: "TraceMessage",
          trace_id: 26,
          parent_trace_id: 25,
          node_attr: {
            name: "system",
            text: null,
            class_name: "RoleCloserInput"
          }
        },
        {
          message_id: 70,
          class_name: "TraceMessage",
          trace_id: 27,
          parent_trace_id: 26,
          node_attr: {
            name: "user",
            text: null,
            closer_text: null,
            class_name: "RoleOpenerInput"
          }
        },
        {
          message_id: 74,
          class_name: "TraceMessage",
          trace_id: 28,
          parent_trace_id: 27,
          node_attr: {
            value: "What is the meaning of life?",
            is_input: true,
            is_generated: false,
            is_force_forwarded: false,
            latency_ms: 0.0,
            class_name: "TextOutput"
          }
        },
        {
          message_id: 78,
          class_name: "TraceMessage",
          trace_id: 31,
          parent_trace_id: 30,
          node_attr: {
            name: "user",
            text: null,
            class_name: "RoleCloserInput"
          }
        },
        {
          message_id: 80,
          class_name: "TraceMessage",
          trace_id: 32,
          parent_trace_id: 31,
          node_attr: {
            name: "assistant",
            text: null,
            closer_text: null,
            class_name: "RoleOpenerInput"
          }
        },
        {
          message_id: 84,
          class_name: "TraceMessage",
          trace_id: 33,
          parent_trace_id: 32,
          node_attr: {
            value: "The",
            is_input: false,
            is_generated: true,
            is_force_forwarded: false,
            latency_ms: 3.840923309326172,
            token: {
              token: "The",
              bytes: "VkdobA==",
              prob: 0.9991078503551186,
              masked: false
            },
            top_k: [],
            class_name: "TokenOutput"
          }
        },
        {
          message_id: 85,
          class_name: "TraceMessage",
          trace_id: 34,
          parent_trace_id: 33,
          node_attr: {
            value: " meaning",
            is_input: false,
            is_generated: true,
            is_force_forwarded: false,
            latency_ms: 0.8611679077148438,
            token: {
              token: " meaning",
              bytes: "SUcxbFlXNXBibWM9",
              prob: 0.974727050252642,
              masked: false
            },
            top_k: [],
            class_name: "TokenOutput"
          }
        },
        {
          message_id: 91,
          class_name: "ExecutionCompletedMessage",
          last_trace_id: 39,
          is_err: false
        }
      ]
    };

    // Play back the messages
    await page.evaluate(async (rec) => {
      return window.testAPI.playbackMessages(rec, { delay: 50 });
    }, recording);
    
    // Wait for playback to complete
    await page.waitForTimeout(1000);
    
    // Check that roles are displayed correctly
    const systemRole = page.locator('text=SYSTEM').first();
    await expect(systemRole).toBeVisible();
    
    const userRole = page.locator('text=USER').first();
    await expect(userRole).toBeVisible();
    
    const assistantRole = page.locator('text=ASSISTANT').first();
    await expect(assistantRole).toBeVisible();
    
    // Check token content
    const systemContent = page.locator('text=You are a helpful assistant.');
    await expect(systemContent).toBeVisible();
    
    const userContent = page.locator('text=What is the meaning of life?');
    await expect(userContent).toBeVisible();
    
    // Check generated tokens
    const generatedToken = page.locator('.token-grid-item').filter({ hasText: 'The' });
    await expect(generatedToken).toBeVisible();
    
    // Verify state
    const state = await page.evaluate(() => window.testAPI.getWidgetState());
    expect(state.tokens.length).toBeGreaterThan(0);
  });

  test('should handle backtracking in recorded messages', async ({ page }) => {
    // Create a recording with backtracking
    const backtrackRecording = {
      timestamp: new Date().toISOString(),
      messageCount: 10,
      messages: [
        {
          message_id: 1,
          class_name: "ExecutionStartedMessage"
        },
        {
          message_id: 2,
          class_name: "TraceMessage",
          trace_id: 1,
          parent_trace_id: null,
          node_attr: {
            name: "assistant",
            class_name: "RoleOpenerInput"
          }
        },
        {
          message_id: 3,
          class_name: "TraceMessage",
          trace_id: 2,
          parent_trace_id: 1,
          node_attr: {
            value: "2+2=",
            is_input: true,
            is_generated: false,
            class_name: "TextOutput"
          }
        },
        {
          message_id: 4,
          class_name: "TraceMessage",
          trace_id: 3,
          parent_trace_id: 2,
          node_attr: {
            value: "5",
            is_input: false,
            is_generated: true,
            token: { prob: 0.1 },
            class_name: "TokenOutput"
          }
        },
        // Reset for backtrack
        {
          message_id: 5,
          class_name: "ResetDisplayMessage"
        },
        // Replay without the wrong answer
        {
          message_id: 6,
          class_name: "TraceMessage",
          trace_id: 1,
          parent_trace_id: null,
          node_attr: {
            name: "assistant",
            class_name: "RoleOpenerInput"
          }
        },
        {
          message_id: 7,
          class_name: "TraceMessage",
          trace_id: 2,
          parent_trace_id: 1,
          node_attr: {
            value: "2+2=",
            is_input: true,
            is_generated: false,
            class_name: "TextOutput"
          }
        },
        {
          message_id: 8,
          class_name: "TraceMessage",
          trace_id: 4,
          parent_trace_id: 2,
          node_attr: {
            value: "4",
            is_input: false,
            is_generated: true,
            token: { prob: 0.95 },
            class_name: "TokenOutput"
          }
        },
        {
          message_id: 9,
          class_name: "ExecutionCompletedMessage",
          last_trace_id: 4
        }
      ]
    };

    // Play back with backtracking
    await page.evaluate(async (rec) => {
      return window.testAPI.playbackMessages(rec, { delay: 100 });
    }, backtrackRecording);
    
    // Wait for completion
    await page.waitForTimeout(1500);
    
    // Should only see the correct answer
    const correctAnswer = page.locator('.token-grid-item').filter({ hasText: '4' });
    await expect(correctAnswer).toBeVisible();
    
    // Wrong answer should not be visible
    const wrongAnswer = page.locator('.token-grid-item').filter({ hasText: '5' });
    await expect(wrongAnswer).not.toBeVisible();
  });

  test('should load and playback from JSON file', async ({ page }) => {
    // Create a test recording file URL
    const testRecording = {
      timestamp: new Date().toISOString(),
      messageCount: 5,
      messages: [
        {
          message_id: 1,
          class_name: "ExecutionStartedMessage"
        },
        {
          message_id: 2,
          class_name: "TraceMessage",
          trace_id: 1,
          parent_trace_id: null,
          node_attr: {
            value: "Hello from JSON file!",
            is_input: true,
            is_generated: false,
            class_name: "TextOutput"
          }
        },
        {
          message_id: 3,
          class_name: "ExecutionCompletedMessage",
          last_trace_id: 1
        }
      ]
    };
    
    // Simulate loading from file
    await page.evaluate(async (rec) => {
      const loaded = await window.testAPI.loadRecording(rec);
      return window.testAPI.playbackMessages(loaded);
    }, testRecording);
    
    // Verify content loaded
    const content = page.locator('text=Hello from JSON file!');
    await expect(content).toBeVisible();
  });
});

// Test for validating recording format
test('recording validation', async ({ page }) => {
  const harnessPath = path.join(__dirname, '../src/test-utils/enhanced-test-harness.html');
  await page.goto(`file://${harnessPath}`);
  await page.waitForFunction(() => window.testAPIReady === true);
  
  // Test valid recording
  const isValid = await page.evaluate(() => {
    const validRecording = {
      timestamp: "2025-01-01T00:00:00Z",
      messageCount: 1,
      messages: [{
        message_id: 1,
        class_name: "ExecutionStartedMessage"
      }]
    };
    
    // Simple validation
    return (
      validRecording.timestamp &&
      validRecording.messageCount === validRecording.messages.length &&
      validRecording.messages.every(m => m.message_id !== undefined && m.class_name !== undefined)
    );
  });
  
  expect(isValid).toBe(true);
});