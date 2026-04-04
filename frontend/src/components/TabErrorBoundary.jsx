/**
 * TabErrorBoundary — Catches lazy-load and render crashes in tabbed views.
 *
 * Without this, a crash in any lazy-loaded tab component causes the entire
 * hub page to go blank with no error visible. With this boundary, the
 * crashed tab shows a diagnostic message while other tabs remain functional.
 */
import { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

class TabErrorBoundary extends Component {
  state = { error: null, errorInfo: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('TabErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-3" />
          <h3 className="text-lg font-semibold text-foreground mb-2">Tab failed to load</h3>
          <p className="text-sm text-muted-foreground mb-3">
            {this.state.error?.message || 'An unexpected error occurred'}
          </p>
          <details className="text-left text-xs text-muted-foreground bg-muted/50 p-3 rounded max-w-lg mx-auto">
            <summary className="cursor-pointer font-medium">Technical details</summary>
            <pre className="mt-2 whitespace-pre-wrap overflow-auto max-h-40">
              {this.state.error?.stack || ''}
              {this.state.errorInfo?.componentStack || ''}
            </pre>
          </details>
          <button
            onClick={() => this.setState({ error: null, errorInfo: null })}
            className="mt-3 px-4 py-2 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default TabErrorBoundary;
