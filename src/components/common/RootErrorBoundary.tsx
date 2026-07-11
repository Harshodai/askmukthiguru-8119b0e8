import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Top-level error boundary. Prevents the dreaded white screen by rendering
 * a branded fallback if React fails to render anywhere in the tree.
 */
export class RootErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[RootErrorBoundary] Render crash:', error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    const message = this.state.error.message || 'Unknown error';
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          background: '#faf6ef',
          color: '#2a1d0d',
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        }}
      >
        <div style={{ maxWidth: 480, textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🪔</div>
          <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: 14, opacity: 0.75, marginBottom: 20 }}>
            AskMukthiGuru hit an unexpected error while loading. Reloading
            usually fixes it.
          </p>
          <details
            style={{
              fontSize: 12,
              textAlign: 'left',
              background: '#fff',
              border: '1px solid #e6dccb',
              borderRadius: 8,
              padding: 12,
              marginBottom: 16,
            }}
          >
            <summary style={{ cursor: 'pointer' }}>Technical details</summary>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                marginTop: 8,
              }}
            >
              {message}
            </pre>
          </details>
          <button
            onClick={this.handleReload}
            style={{
              background: '#b8862a',
              color: '#fff',
              border: 0,
              padding: '10px 20px',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
