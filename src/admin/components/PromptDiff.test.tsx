import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { PromptDiff } from "./PromptDiff";

describe("PromptDiff", () => {
  it("renders without crashing with valid inputs", () => {
    const { container } = render(<PromptDiff a="hello\nworld" b="hello\nthere\nworld" />);
    expect(container).toBeInTheDocument();
  });

  it("handles null or undefined gracefully without crashing", () => {
    const { container: c1 } = render(<PromptDiff a={null} b={null} />);
    expect(c1).toBeInTheDocument();

    const { container: c2 } = render(<PromptDiff a={undefined} b="some prompt" />);
    expect(c2).toBeInTheDocument();

    const { container: c3 } = render(<PromptDiff a="some prompt" b={undefined} />);
    expect(c3).toBeInTheDocument();
  });

  it("handles empty strings", () => {
    const { container } = render(<PromptDiff a="" b="" />);
    expect(container).toBeInTheDocument();
  });
});
