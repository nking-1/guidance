/**
 * Message playback utilities for testing the guidance widget with real recorded messages
 */

import type { GuidanceMessage, TraceMessage, NodeAttr } from '../stitch';

export interface DebugRecording {
  timestamp: string;
  messageCount: number;
  messages: GuidanceMessage[];
}

export interface PlaybackOptions {
  /** Delay between messages in milliseconds (0 for instant) */
  messageDelay?: number;
  /** Whether to skip non-visual messages */
  skipNonVisual?: boolean;
  /** Whether to reset widget before playback */
  resetFirst?: boolean;
}

/**
 * Convert recorded debug messages to simplified test format
 * This extracts just the visual components for testing
 */
export function extractComponentsFromRecording(recording: DebugRecording): NodeAttr[] {
  const components: NodeAttr[] = [];
  
  // Extract node_attr from TraceMessages
  recording.messages.forEach(msg => {
    if (msg.class_name === 'TraceMessage') {
      const traceMsg = msg as TraceMessage;
      if (traceMsg.node_attr) {
        components.push(traceMsg.node_attr);
      }
    }
  });
  
  return components;
}

/**
 * Play back recorded messages to the widget
 * This simulates the actual message flow from the Python side
 */
export async function playbackMessages(
  messages: GuidanceMessage[], 
  widget: any, // The actual widget instance
  options: PlaybackOptions = {}
): Promise<void> {
  const { 
    messageDelay = 0, 
    skipNonVisual = false,
    resetFirst = true 
  } = options;
  
  if (resetFirst) {
    // Send reset message first
    await sendMessage(widget, {
      message_id: -1,
      class_name: 'ResetDisplayMessage'
    });
  }
  
  // Play back each message
  for (const message of messages) {
    // Skip non-visual messages if requested
    if (skipNonVisual && !isVisualMessage(message)) {
      continue;
    }
    
    await sendMessage(widget, message);
    
    if (messageDelay > 0) {
      await delay(messageDelay);
    }
  }
}

/**
 * Create a test scenario from a recorded debug session
 */
export function createTestScenario(name: string, recording: DebugRecording) {
  return {
    name,
    recording,
    components: extractComponentsFromRecording(recording),
    
    // Helper methods for testing
    async playback(widget: any, options?: PlaybackOptions) {
      return playbackMessages(recording.messages, widget, options);
    },
    
    getComponents() {
      return this.components;
    },
    
    findMessagesByType(className: string) {
      return recording.messages.filter(msg => msg.class_name === className);
    },
    
    findTraceMessages() {
      return recording.messages.filter(msg => msg.class_name === 'TraceMessage') as TraceMessage[];
    },
    
    getRoleSequence() {
      const roles: string[] = [];
      this.components.forEach(comp => {
        if (comp.class_name === 'RoleOpenerInput') {
          roles.push((comp as any).name || 'unknown');
        }
      });
      return roles;
    },
    
    getTokenCount() {
      return this.components.filter(comp => 
        comp.class_name === 'TokenOutput' || comp.class_name === 'TextOutput'
      ).length;
    }
  };
}

/**
 * Load a recorded debug session from a JSON file path or object
 */
export async function loadRecording(pathOrData: string | DebugRecording): Promise<DebugRecording> {
  if (typeof pathOrData === 'string') {
    // In browser context, we'd need to fetch
    const response = await fetch(pathOrData);
    return await response.json();
  }
  return pathOrData;
}

/**
 * Validate that a recording has the expected structure
 */
export function validateRecording(recording: any): recording is DebugRecording {
  return (
    recording &&
    typeof recording.timestamp === 'string' &&
    typeof recording.messageCount === 'number' &&
    Array.isArray(recording.messages) &&
    recording.messages.every((msg: any) => 
      msg.message_id !== undefined && 
      msg.class_name !== undefined
    )
  );
}

// Helper functions

function isVisualMessage(message: GuidanceMessage): boolean {
  const visualTypes = [
    'TraceMessage', 
    'ResetDisplayMessage', 
    'ExecutionStartedMessage',
    'ExecutionCompletedMessage',
    'MetricMessage'
  ];
  return visualTypes.includes(message.class_name);
}

async function sendMessage(widget: any, message: GuidanceMessage): Promise<void> {
  // This would send the message to the actual widget
  // Implementation depends on how the widget receives messages
  if (widget && widget.handleMessage) {
    widget.handleMessage(message);
  } else if (window.testAPI && window.testAPI.sendMessage) {
    window.testAPI.sendMessage(message);
  } else {
    console.warn('No message handler available', message);
  }
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Export for use in tests
export default {
  extractComponentsFromRecording,
  playbackMessages,
  createTestScenario,
  loadRecording,
  validateRecording
};