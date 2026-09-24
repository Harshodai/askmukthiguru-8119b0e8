import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  PromptInput,
  PromptInputTextarea,
} from '@/components/ai-elements/prompt-input';
import React from 'react';

/**
 * Keyboard contract tests for PromptInputTextarea.
 *
 * JSDOM note: form.requestSubmit() does not propagate to React's onSubmit in
 * jsdom. We spy on HTMLFormElement.prototype.requestSubmit to verify it is
 * called (or not called) without needing a full React form submission cycle.
 */

function makeComposer(onSubmit = vi.fn()) {
  return render(
    <PromptInput onSubmit={onSubmit}>
      <PromptInputTextarea aria-label="test-textarea" placeholder="type here" />
      <button type="submit" aria-label="send">Send</button>
    </PromptInput>,
  );
}

describe('PromptInputTextarea keyboard contract', () => {
  let requestSubmitSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Spy on form.requestSubmit so we can assert it is called once per Enter.
    requestSubmitSpy = vi.spyOn(HTMLFormElement.prototype, 'requestSubmit').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('Enter calls form.requestSubmit exactly once', () => {
    makeComposer();
    const ta = screen.getByLabelText('test-textarea') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'hello' } });
    fireEvent.keyDown(ta, { key: 'Enter', code: 'Enter' });
    expect(requestSubmitSpy).toHaveBeenCalledTimes(1);
  });

  it('Shift+Enter does NOT call form.requestSubmit', () => {
    makeComposer();
    const ta = screen.getByLabelText('test-textarea') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'hello' } });
    fireEvent.keyDown(ta, { key: 'Enter', code: 'Enter', shiftKey: true });
    expect(requestSubmitSpy).not.toHaveBeenCalled();
  });

  it('Enter with nativeEvent.isComposing=true does NOT submit', () => {
    makeComposer();
    const ta = screen.getByLabelText('test-textarea') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'あ' } });
    // Dispatch a keydown event with isComposing=true on the native event.
    // React wraps the native event, so e.nativeEvent.isComposing will be true.
    const ev = new KeyboardEvent('keydown', {
      key: 'Enter',
      code: 'Enter',
      bubbles: true,
      cancelable: true,
      isComposing: true,
    });
    ta.dispatchEvent(ev);
    expect(requestSubmitSpy).not.toHaveBeenCalled();
  });

  it('Enter during IME composition (compositionstart fired) does NOT submit', () => {
    makeComposer();
    const ta = screen.getByLabelText('test-textarea') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'あ' } });
    // Fire compositionStart to set internal isComposing React state
    fireEvent.compositionStart(ta);
    fireEvent.keyDown(ta, { key: 'Enter', code: 'Enter' });
    expect(requestSubmitSpy).not.toHaveBeenCalled();
    // compositionEnd clears composing state
    fireEvent.compositionEnd(ta);
  });

  it('Enter when submit button is disabled does NOT submit', () => {
    const onSubmit = vi.fn();
    render(
      <PromptInput onSubmit={onSubmit}>
        <PromptInputTextarea aria-label="test-textarea" placeholder="type here" />
        <button type="submit" aria-label="send" disabled>Send</button>
      </PromptInput>,
    );
    const ta = screen.getByLabelText('test-textarea') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'hello' } });
    fireEvent.keyDown(ta, { key: 'Enter', code: 'Enter' });
    expect(requestSubmitSpy).not.toHaveBeenCalled();
  });

  it('outer onKeyDown that does NOT preventDefault still results in exactly one submit (regression guard)', () => {
    // This proves the fix: outer handler that does not call preventDefault
    // lets PromptInputTextarea own the submit — no double-submit.
    const outerKeyDown = vi.fn();
    render(
      <PromptInput onSubmit={vi.fn()}>
        <PromptInputTextarea
          aria-label="test-textarea"
          placeholder="type here"
          onKeyDown={outerKeyDown}
        />
        <button type="submit" aria-label="send">Send</button>
      </PromptInput>,
    );
    const ta = screen.getByLabelText('test-textarea') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'hello' } });
    fireEvent.keyDown(ta, { key: 'Enter', code: 'Enter' });
    // outer handler called once
    expect(outerKeyDown).toHaveBeenCalledTimes(1);
    // requestSubmit called exactly once (not twice)
    expect(requestSubmitSpy).toHaveBeenCalledTimes(1);
  });
});
