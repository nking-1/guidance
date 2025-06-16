# Widget Testing Guide

This guide explains how testing is set up for the guidance widget, how the mock data system works, and how to run tests.

## Overview

The widget uses **Playwright for browser-based testing** with a **dynamic mock data injection system**. This approach tests the actual widget behavior in real browsers without the complexity of setting up full Jupyter notebook environments.

## Architecture

### Test Components

```
tests/                          # Playwright test files
├── smoke.spec.js              # Basic functionality test
└── backtrack-fix.spec.js      # Tests for backtracking bug fix

src/test-utils/                # Testing utilities
├── test-harness.html          # Test environment (loads widget + injection API)
├── mock-generator.ts          # Dynamic mock data creation system
├── dev-integration.ts         # Predefined test scenarios for development
├── example-tests.ts           # Example test patterns (reference)
└── demo.html                  # Manual mock data viewer

playwright.config.js           # Playwright configuration
```

## How Mock Data Injection Works

### Data Flow

```
Test File (JavaScript)
    ↓ (injects mock data)
Test Harness (HTML + test API)
    ↓ (renders with mock data)
Widget DOM (actual rendered tokens/roles)
    ↓ (assertions check)
Test Results
```

### Mock Data Structure

Mock data consists of arrays of components that simulate the guidance library's output:

```javascript
// Basic token
{
  "class_name": "TextOutput",
  "value": "Hello",
  "is_input": false,
  "is_generated": true,
  "prob": 0.9
}

// Role opener
{
  "class_name": "RoleOpenerInput", 
  "name": "user",
  "text": "<|user|>\n",
  "closer_text": "<|end|>\n"
}

// Backtrack event
{
  "class_name": "Backtrack",
  "n_tokens": 1,
  "bytes": "ZmFrZS1kYXRh"
}
```

### Mock Generator System

The `mock-generator.ts` provides a fluent API for creating test scenarios:

```javascript
import { mockGenerator } from './src/test-utils/mock-generator';

// Simple conversation
const components = mockGenerator()
  .addRole({
    name: "user",
    tokens: [{ text: "Hello" }]
  })
  .addRole({
    name: "assistant", 
    tokens: [
      { text: "Hi", prob: 0.9, is_generated: true },
      { text: " there!", prob: 0.8, is_generated: true }
    ]
  })
  .build();

// Backtracking scenario
const backtrackTest = mockGenerator()
  .addRole({
    name: "assistant",
    tokens: [
      { text: "2+2=", prob: 0.9 },
      { text: "5", prob: 0.1 }  // Wrong answer
    ]
  })
  .addBacktrack({ n_tokens: 1, at_position: -1 })  // Remove "5"
  .addTokens([{ text: "4", prob: 0.95 }])           // Correct answer
  .build();
```

### Test Harness API

The test harness (`test-harness.html`) exposes a `window.testAPI` object:

```javascript
// Inject mock data and render widget
await page.evaluate((mockData) => {
  return window.testAPI.injectMockData('test-name', mockData);
}, mockComponents);

// Wait for widget to be ready
await page.evaluate(() => window.testAPI.waitForWidget());

// Get current widget state for assertions
const state = await page.evaluate(() => window.testAPI.getWidgetState());
// Returns: { tokens: [...], roles: [...], backtracks: [...] }
```

### Visual Rendering

The test harness renders a simplified but functional version of the widget:

- **Tokens**: Displayed as spans with role, probability, and generation info
- **Roles**: Shown as colored headers (blue for user, purple for assistant)  
- **Backtrack Events**: Red indicators showing number of tokens removed
- **Probabilities**: Mapped to opacity (higher prob = more opaque)
- **Click Handlers**: Tokens log debug info when clicked

## Running Tests

### Prerequisites

```bash
# Install dependencies (already done if you've built the widget)
npm install

# Install Playwright browsers (only needed once)
npx playwright install chromium  # Or firefox, webkit
```

### Test Commands

```bash
# Run all tests
npm test

# Run specific test file
npm test tests/smoke.spec.js

# Run with specific browser
npm test -- --project=chromium

# Visual test runner (interactive)
npm run test:ui

# Debug mode (step through tests)
npm run test:debug

# Run tests and open report
npm test && npx playwright show-report
```

### Manual Testing

```bash
# Interactive mock data viewer
npm run test:mock-demo
# Then open http://localhost:3001/demo.html

# Development server with widget
npm run dev
# Edit App.svelte to use mock data scenarios
```

## Writing Tests

### Basic Test Structure

```javascript
const { test, expect } = require('@playwright/test');

test.describe('Feature Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to test harness
    await page.goto(`file://${__dirname}/../src/test-utils/test-harness.html`);
    
    // Wait for test API
    await page.waitForFunction(() => window.testAPIReady === true);
  });

  test('should handle specific scenario', async ({ page }) => {
    // Create mock data
    const mockData = [/* your mock components */];
    
    // Inject data
    await page.evaluate((data) => {
      return window.testAPI.injectMockData('scenario-name', data);
    }, mockData);
    
    // Wait for rendering
    await page.evaluate(() => window.testAPI.waitForWidget());
    
    // Test assertions
    const token = page.locator('.token').filter({ hasText: 'expected text' });
    await expect(token).toBeVisible();
    
    // Check widget state
    const state = await page.evaluate(() => window.testAPI.getWidgetState());
    expect(state.tokens).toHaveLength(expectedCount);
  });
});
```

### Test Categories

**Smoke Tests** (`smoke.spec.js`)
- Basic functionality
- API availability
- Simple rendering

**Backtrack Tests** (`backtrack-fix.spec.js`)  
- Role assignment after backtracking
- Token removal/replay scenarios
- Visual probability rendering
- Performance with large sequences

**Custom Tests**
- Add new `.spec.js` files in `tests/` directory
- Use mock generator for data creation
- Focus on specific widget behaviors

### Debugging Tests

```bash
# Run single test in debug mode
npm run test:debug -- tests/smoke.spec.js

# Add console.log in test
await page.evaluate(() => {
  console.log('Debug info:', window.testAPI.getWidgetState());
});

# Take screenshots
await page.screenshot({ path: 'debug.png' });

# Inspect element
await page.locator('.token').first().highlight();
```

## Mock Data Scenarios

### Predefined Scenarios

The `dev-integration.ts` file contains ready-made scenarios:

- `simple` - Basic user/assistant conversation
- `backtrackFix` - Tests the role assignment bug fix
- `roleConfusion` - Backtrack causing role misalignment  
- `multimodal` - Images, audio, video content
- `probabilities` - Various token confidence levels
- `edgeCases` - Empty tokens, special characters

### Creating Custom Scenarios

```javascript
// In your test file or dev-integration.ts
const customScenario = mockGenerator()
  .addRole({ name: "user", tokens: [{ text: "Custom input" }] })
  .addImage("png", "base64data...")  // Optional media
  .addRole({ 
    name: "assistant",
    tokens: [
      { text: "Response", prob: 0.9, is_generated: true },
      { text: " part", prob: 0.7, is_generated: true }
    ]
  })
  .addBacktrack({ n_tokens: 1, at_position: -1 })  // Remove last token
  .addTokens([{ text: " better", prob: 0.95, is_generated: true }])
  .build();
```

## Best Practices

### Test Organization
- One test file per major feature area
- Use descriptive test names
- Group related tests with `test.describe()`

### Mock Data
- Use realistic probability values (0.0 - 1.0)
- Include proper role sequences (opener → content → closer)
- Test edge cases (empty strings, special characters)

### Assertions
- Test both DOM presence and widget state
- Verify visual properties (colors, opacity)
- Check data attributes for debugging

### Performance
- Keep test data reasonably sized (< 100 tokens for most tests)
- Use `test.skip()` for slow tests during development
- Parallelize independent tests

## Troubleshooting

### Common Issues

**Test timeouts**
- Increase timeout: `--timeout=60000`
- Check browser console for errors
- Verify mock data structure

**Widget not rendering**
- Check `window.testAPIReady` is true
- Verify bundle.js loads correctly
- Inspect browser developer tools

**Mock data not appearing**
- Validate mock data structure matches expected format
- Check console for injection errors
- Use `getWidgetState()` to debug

**Browser differences**
- Run specific browser: `--project=chromium`
- Check CSS compatibility issues
- Test with multiple browsers for critical features

### Getting Help

1. Run smoke test first: `npm test tests/smoke.spec.js`
2. Check test harness manually: `npm run test:mock-demo`
3. Use debug mode: `npm run test:debug`
4. Inspect generated HTML report: `npx playwright show-report`

## Future Enhancements

- **Visual regression testing** - Screenshot comparisons
- **Jupyter integration tests** - Test actual notebook communication  
- **Performance benchmarks** - Automated performance monitoring
- **Accessibility tests** - Screen reader and keyboard navigation
- **Mobile testing** - Touch interactions and responsive design