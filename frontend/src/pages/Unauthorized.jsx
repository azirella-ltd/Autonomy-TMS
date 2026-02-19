import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { Button, Alert, Badge } from '../components/common';
import { cn } from '../lib/utils/cn';

const Unauthorized = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const requiredCapability = location.state?.requiredCapability;

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <Lock className="h-20 w-20 text-destructive mb-4" />

      <h1 className="text-3xl font-bold text-foreground mb-2">
        Access Denied
      </h1>

      <p className="text-muted-foreground text-center max-w-xl mb-4">
        You don't have permission to access this page.
      </p>

      {requiredCapability && (
        <Alert variant="info" className="mt-4 max-w-xl">
          <p className="text-sm">
            This page requires the following capability:
          </p>
          <Badge
            variant="outline"
            className="mt-2 font-mono"
          >
            {requiredCapability}
          </Badge>
          <p className="text-sm mt-4">
            Please contact your Group Admin to request access.
          </p>
        </Alert>
      )}

      <div className="mt-6 flex flex-wrap gap-3 justify-center">
        <Button variant="default" onClick={() => navigate('/')}>
          Go to Dashboard
        </Button>
        <Button variant="outline" onClick={() => navigate(-1)}>
          Go Back
        </Button>
        <Button variant="outline" onClick={() => navigate('/login', { state: { from: location } })}>
          Login With Different Account
        </Button>
      </div>
    </div>
  );
};

export default Unauthorized;
