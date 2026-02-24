/**
 * Training Leaderboards Page
 *
 * Displays leaderboards for learning mode users to track their
 * performance against other users.
 *
 * NOTE: This is named "Training" for the route path, but it's part of
 * the Learning group experience (user education), not AI model training.
 */

import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import LeaderboardPanel from '../../components/scenario/LeaderboardPanel';

const TrainingLeaderboards = () => {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Leaderboards</h1>
        <p className="text-muted-foreground mt-1">
          See how you rank against other users in your learning group
        </p>
      </div>

      {/* Leaderboard Content */}
      <LeaderboardPanel scenarioUserId={user?.id} />
    </div>
  );
};

export default TrainingLeaderboards;
