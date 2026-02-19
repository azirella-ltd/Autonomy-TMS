import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common';
import { Home } from 'lucide-react';

const NotFound = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-center p-6 bg-background">
      <h1 className="text-8xl font-bold text-primary mb-4">
        404
      </h1>
      <h2 className="text-3xl font-semibold text-foreground mb-4">
        Page Not Found
      </h2>
      <p className="text-muted-foreground mb-8 max-w-md">
        The page you are looking for might have been removed, had its name changed, or is temporarily unavailable.
      </p>
      <Button onClick={() => navigate('/')} size="lg">
        <Home className="h-4 w-4 mr-2" />
        Go to Homepage
      </Button>
    </div>
  );
};

export default NotFound;
