import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error?: Error;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {};

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('React render error', error, errorInfo);
  }

  private reloadApp = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <main className="flex min-h-screen items-center justify-center bg-mist px-5 py-8">
        <section className="w-full max-w-xl rounded-lg border border-slate-200 bg-white p-6 shadow-panel">
          <p className="text-sm font-medium uppercase tracking-wide text-trail">Travel Agent Cloud</p>
          <h1 className="mt-2 text-2xl font-semibold text-ink">The workspace could not render</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Reload the app to recover. If this keeps happening, keep the console error and report the action that caused it.
          </p>
          {import.meta.env.DEV && (
            <pre className="mt-4 max-h-48 overflow-auto rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-100">
              {this.state.error.message}
            </pre>
          )}
          <button
            type="button"
            onClick={this.reloadApp}
            className="mt-5 rounded-md bg-trail px-4 py-2 text-sm font-medium text-white transition hover:bg-trail/90"
          >
            Reload app
          </button>
        </section>
      </main>
    );
  }
}
