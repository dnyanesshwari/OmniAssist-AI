import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

class AppErrorBoundary extends React.Component<React.PropsWithChildren, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Frontend render failed", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return <div className="center"><section className="card">
        <h2>The page could not load</h2>
        <p className="err">{this.state.error.message}</p>
        <button onClick={() => window.location.reload()}>Reload page</button>
      </section></div>;
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <AppErrorBoundary><App /></AppErrorBoundary>,
);
