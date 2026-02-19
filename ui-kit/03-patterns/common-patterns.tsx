/**
 * Common UI Patterns - Copy-Paste Ready Code Blocks
 *
 * These are production-ready patterns from the Autonomy Prototype.
 * Copy and adapt these to your needs.
 */

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../02-components/ui/card";
import { Button } from "../02-components/ui/button";
import { Input } from "../02-components/ui/input";
import { Label } from "../02-components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "../02-components/ui/alert";
import { Badge } from "../02-components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../02-components/ui/dialog";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";

// ============================================================================
// KPI Dashboard Layout
// ============================================================================

export function KPIDashboardPattern() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card>
        <CardHeader className="p-6">
          <CardDescription>Total Sales</CardDescription>
          <CardTitle className="text-3xl">$1,234,567</CardTitle>
        </CardHeader>
        <CardContent className="p-6 pt-0">
          <p className="text-sm text-emerald-600">+12% from last month</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="p-6">
          <CardDescription>Active Users</CardDescription>
          <CardTitle className="text-3xl">8,234</CardTitle>
        </CardHeader>
        <CardContent className="p-6 pt-0">
          <p className="text-sm text-emerald-600">+8% from last month</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="p-6">
          <CardDescription>Conversion Rate</CardDescription>
          <CardTitle className="text-3xl">4.2%</CardTitle>
        </CardHeader>
        <CardContent className="p-6 pt-0">
          <p className="text-sm text-red-600">-2% from last month</p>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================================
// Form with Validation
// ============================================================================

export function FormPattern() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>User Information</CardTitle>
        <CardDescription>Update your profile details</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input id="name" placeholder="John Doe" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" placeholder="john@example.com" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bio">Bio</Label>
            <textarea
              id="bio"
              className="w-full p-2 border rounded-md min-h-[100px]"
              placeholder="Tell us about yourself"
            />
          </div>
        </form>
      </CardContent>
      <CardFooter className="flex justify-end gap-2">
        <Button variant="outline">Cancel</Button>
        <Button>Save Changes</Button>
      </CardFooter>
    </Card>
  );
}

// ============================================================================
// Data Table with Actions
// ============================================================================

export function DataTablePattern() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Orders</CardTitle>
        <CardDescription>View and manage recent customer orders</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="p-4 text-left font-medium">Order ID</th>
                <th className="p-4 text-left font-medium">Customer</th>
                <th className="p-4 text-left font-medium">Status</th>
                <th className="p-4 text-left font-medium">Amount</th>
                <th className="p-4 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b">
                <td className="p-4">#12345</td>
                <td className="p-4">John Doe</td>
                <td className="p-4">
                  <Badge>Completed</Badge>
                </td>
                <td className="p-4">$1,234.00</td>
                <td className="p-4">
                  <Button variant="ghost" size="sm">View</Button>
                </td>
              </tr>
              <tr className="border-b">
                <td className="p-4">#12346</td>
                <td className="p-4">Jane Smith</td>
                <td className="p-4">
                  <Badge variant="secondary">Pending</Badge>
                </td>
                <td className="p-4">$567.00</td>
                <td className="p-4">
                  <Button variant="ghost" size="sm">View</Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Modal Dialog
// ============================================================================

export function ModalDialogPattern() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button>Open Dialog</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm Action</DialogTitle>
          <DialogDescription>
            Are you sure you want to proceed with this action? This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline">Cancel</Button>
          <Button variant="destructive">Confirm</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Loading States
// ============================================================================

export function LoadingStatePattern() {
  return (
    <Card>
      <CardHeader>
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-4 w-64 bg-muted animate-pulse rounded mt-2" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="h-4 w-full bg-muted animate-pulse rounded" />
          <div className="h-4 w-full bg-muted animate-pulse rounded" />
          <div className="h-4 w-3/4 bg-muted animate-pulse rounded" />
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Empty States
// ============================================================================

export function EmptyStatePattern() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center py-12">
        <div className="rounded-full bg-muted p-4 mb-4">
          <Info className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold mb-2">No data available</h3>
        <p className="text-sm text-muted-foreground mb-4 text-center max-w-sm">
          We couldn't find any data to display. Try adjusting your filters or create a new entry.
        </p>
        <Button>Create New</Button>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Status Alerts
// ============================================================================

export function StatusAlertsPattern() {
  return (
    <div className="space-y-4">
      {/* Error Alert */}
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>
          Your session has expired. Please log in again.
        </AlertDescription>
      </Alert>

      {/* Success Alert */}
      <Alert className="border-emerald-200 bg-emerald-50">
        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
        <AlertTitle className="text-emerald-900">Success</AlertTitle>
        <AlertDescription className="text-emerald-800">
          Your changes have been saved successfully.
        </AlertDescription>
      </Alert>

      {/* Info Alert */}
      <Alert className="border-blue-200 bg-blue-50">
        <Info className="h-4 w-4 text-blue-600" />
        <AlertTitle className="text-blue-900">Information</AlertTitle>
        <AlertDescription className="text-blue-800">
          New features are available. Check them out in the settings.
        </AlertDescription>
      </Alert>
    </div>
  );
}
