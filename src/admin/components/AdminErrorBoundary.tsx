import { Component, type ReactNode } from "react";
import { AlertCircle, RotateCcw, Home } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  children: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class AdminErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[AdminErrorBoundary]", error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
          <Card className="w-full max-w-lg">
            <CardContent className="p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-destructive/15 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Something went wrong</h2>
                  <p className="text-sm text-muted-foreground">
                    This admin page crashed. The rest of the console is still running.
                  </p>
                </div>
              </div>

              <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
                <AlertTitle>Error details</AlertTitle>
                <AlertDescription className="font-mono text-xs break-all">
                  {this.state.error?.message ?? "Unknown error"}
                </AlertDescription>
              </Alert>

              <div className="flex gap-2">
                <Button onClick={this.handleReset}>
                  <RotateCcw className="h-4 w-4 mr-1.5" />
                  Try again
                </Button>
                <Button variant="outline" asChild>
                  <a href="/admin">
                    <Home className="h-4 w-4 mr-1.5" />
                    Go to Overview
                  </a>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}
