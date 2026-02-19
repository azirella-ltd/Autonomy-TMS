import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LucideIcon } from "lucide-react";

interface KPICardProps {
  icon: LucideIcon;
  iconColor?: "destructive" | "primary" | "info";
  title: string;
  value: string | number;
  subtitle: string;
  actionText?: string;
  onAction?: () => void;
}

export function KPICard({ 
  icon: Icon, 
  iconColor = "primary", 
  title, 
  value, 
  subtitle, 
  actionText,
  onAction 
}: KPICardProps) {
  const iconColorClass = {
    destructive: "text-destructive bg-red-100 p-2 rounded",
    primary: "text-primary bg-lime-100 p-2 rounded",
    info: "text-indigo-600 bg-indigo-100 p-2 rounded"
  }[iconColor];

  return (
    <Card>
      <div className="flex flex-col space-y-1.5 p-6 pb-3">
        <div className="flex items-start gap-3">
          <div className={`mt-1 ${iconColorClass}`}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <div className="text-2xl font-bold text-foreground">{value}</div>
            <div className="text-sm font-medium text-foreground mt-1">
              {title}
            </div>
            <div className="mt-2">
              <p className="text-xs text-muted-foreground">{subtitle}</p>
              {actionText && (
                <Button 
                  variant="link" 
                  className="h-auto p-0 text-info hover:text-info/80 text-xs font-normal"
                  onClick={onAction}
                >
                  {actionText}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
