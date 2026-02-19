import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
} from '../../components/common';
import {
  MessageCircle,
  TrendingUp,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
} from 'lucide-react';

/**
 * Demand Collaboration Page
 *
 * Collaborative Planning, Forecasting, and Replenishment (CPFR)
 * - Share demand forecasts with trading partners
 * - Consensus planning workflows
 * - Approval/rejection workflows
 * - Exception detection
 *
 * AWS SC Entity: demand_collaboration
 * Backend API: /api/v1/demand-collaboration
 */
const DemandCollaboration = () => {
  const [selectedTab, setSelectedTab] = useState(0);

  // Placeholder data
  const summaryStats = {
    total: 45,
    draft: 8,
    submitted: 12,
    approved: 20,
    rejected: 3,
    exceptions: 7,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageCircle className="h-8 w-8" />
          Demand Collaboration (CPFR)
        </h1>
        <p className="text-sm text-muted-foreground">
          Collaborative Planning, Forecasting, and Replenishment with trading partners
        </p>
      </div>

      <Alert variant="info" className="mb-6">
        <strong>Collaborative Forecasting:</strong> Share demand forecasts with suppliers and customers.
        Submit proposals for approval, track exceptions, and monitor forecast accuracy.
      </Alert>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Collaborations</p>
            <p className="text-3xl font-bold">{summaryStats.total}</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <Clock className="h-4 w-4" />
              Draft
            </p>
            <p className="text-3xl font-bold">{summaryStats.draft}</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-4 w-4" />
              Submitted
            </p>
            <p className="text-3xl font-bold">{summaryStats.submitted}</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <CheckCircle className="h-4 w-4 text-green-500" />
              Approved
            </p>
            <p className="text-3xl font-bold text-green-600">{summaryStats.approved}</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <XCircle className="h-4 w-4 text-red-500" />
              Rejected
            </p>
            <p className="text-3xl font-bold text-red-600">{summaryStats.rejected}</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Exceptions
            </p>
            <p className="text-3xl font-bold text-amber-600">{summaryStats.exceptions}</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Card>
        <CardContent className="pt-4">
          <h2 className="text-lg font-semibold mb-4">Demand Collaboration Management</h2>

          <Alert variant="warning" className="mb-4">
            <strong>Full UI Coming Soon</strong>
          </Alert>

          <div className="space-y-4">
            <div>
              <h3 className="font-medium mb-2">Key Features:</h3>
              <ul className="list-disc list-inside text-sm space-y-1 text-muted-foreground">
                <li><strong>Collaborative Forecasting:</strong> Share demand forecasts with suppliers and customers</li>
                <li><strong>Consensus Planning:</strong> Multi-party approval workflows for forecast alignment</li>
                <li><strong>Exception Management:</strong> Automatic detection of large forecast variances (threshold: 20%)</li>
                <li><strong>Version Control:</strong> Track all forecast revisions and changes</li>
                <li><strong>Approval Workflows:</strong> Submit → Review → Approve/Reject cycle</li>
                <li><strong>Forecast Accuracy:</strong> Track actual vs forecasted demand for continuous improvement</li>
              </ul>
            </div>

            <div>
              <h3 className="font-medium mb-2">Backend API Available:</h3>
              <div className="bg-muted p-4 rounded font-mono text-sm space-y-1">
                <div>POST   /api/v1/demand-collaboration - Create collaboration record</div>
                <div>POST   /api/v1/demand-collaboration/bulk - Bulk create</div>
                <div>GET    /api/v1/demand-collaboration - List with filtering</div>
                <div>GET    /api/v1/demand-collaboration/:id - Get by ID</div>
                <div>GET    /api/v1/demand-collaboration/exceptions/detect - Find exceptions</div>
                <div>POST   /api/v1/demand-collaboration/:id/submit - Submit for approval</div>
                <div>POST   /api/v1/demand-collaboration/:id/approve - Approve</div>
                <div>POST   /api/v1/demand-collaboration/:id/reject - Reject</div>
                <div>PUT    /api/v1/demand-collaboration/:id - Update</div>
                <div>DELETE /api/v1/demand-collaboration/:id - Delete</div>
              </div>
            </div>

            <div>
              <h3 className="font-medium mb-2">Collaboration Types:</h3>
              <div className="flex gap-2 flex-wrap">
                <Badge>Forecast Share</Badge>
                <Badge variant="secondary">Consensus</Badge>
                <Badge variant="warning">Alert</Badge>
                <Badge variant="destructive">Exception</Badge>
              </div>
            </div>

            <div>
              <h3 className="font-medium mb-2">Status Flow:</h3>
              <div className="flex gap-2 flex-wrap items-center text-sm">
                <Badge variant="secondary">Draft</Badge>
                <span>→</span>
                <Badge variant="info">Submitted</Badge>
                <span>→</span>
                <Badge variant="success">Approved</Badge>
                <span>/</span>
                <Badge variant="destructive">Rejected</Badge>
                <span>→</span>
                <Badge variant="warning">Revised</Badge>
              </div>
            </div>

            <div className="pt-4">
              <Button disabled>
                Create Collaboration (Coming Soon)
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default DemandCollaboration;
