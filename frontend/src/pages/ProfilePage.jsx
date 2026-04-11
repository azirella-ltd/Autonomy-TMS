import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  Card,
  CardHeader,
  CardContent,
  CardTitle,
  CardDescription,
  Button,
  Input,
  Label,
  FormField,
  Textarea,
  Spinner,
  Badge,
  Alert,
  Skeleton,
  Tabs,
  TabsList,
  Tab,
  TabPanel,
  Select,
  SelectOption,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/common';
import {
  User,
  Trophy,
  BarChart3,
  Calendar,
  Pencil,
  Check,
  X,
  ShieldCheck,
  Clock,
  Target,
  Flame,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';

const ProfilePage = () => {
  const { user, updateProfile } = useAuth();
  const [profile, setProfile] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    bio: '',
    avatar: ''
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  // Fetch user profile and leaderboard data
  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);

        // In a real app, these would be actual API calls
        // For now, we'll use mock data
        const mockProfile = {
          id: user?.id,
          username: user?.username || 'johndoe',
          email: user?.email || 'john@example.com',
          bio: 'Supply chain enthusiast and simulation expert. Always looking for new challenges!',
          avatar: user?.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(user?.username || 'User')}&background=random`,
          joinDate: '2023-01-15T10:30:00Z',
          stats: {
            scenariosCompleted: 42,
            scenariosWon: 28,
            winRate: 67,
            averageScore: 1245,
            totalPlayTime: '3d 7h 22m',
            currentStreak: 5,
            highestStreak: 8,
            rank: 7,
            totalScenarioUsers: 1245,
          },
          achievements: [
            { id: 1, name: 'First Win', description: 'Win your first game', icon: 'trophy', earned: true, date: '2023-01-20' },
            { id: 2, name: 'Supply Chain Master', description: 'Win 25 games', icon: 'medal', earned: true, date: '2023-03-15' },
            { id: 3, name: 'Perfect Game', description: 'Win a scenario with maximum score', icon: 'star', earned: false },
            { id: 4, name: 'Marathoner', description: 'Play for more than 10 hours', icon: 'clock', earned: true, date: '2023-04-02' },
            { id: 5, name: 'Social Butterfly', description: 'Play with 50 different users', icon: 'users', earned: false },
          ],
          recentGames: [
            { id: 101, name: 'Supply Chain Masters', status: 'won', score: 1450, position: 1, date: '2023-05-15T14:30:00Z' },
            { id: 102, name: 'Distribution Challenge', status: 'lost', score: 980, position: 3, date: '2023-05-14T10:15:00Z' },
            { id: 103, name: 'Logistics Challenge', status: 'won', score: 1320, position: 2, date: '2023-05-12T16:45:00Z' },
            { id: 104, name: 'Supply Chain Newbies', status: 'won', score: 1560, position: 1, date: '2023-05-10T09:20:00Z' },
            { id: 105, name: 'Supply Chain Pro', status: 'lost', score: 890, position: 4, date: '2023-05-08T11:30:00Z' },
          ]
        };

        const mockLeaderboard = [
          { id: 1, username: 'supplychainmaster', score: 24560, scenariosCompleted: 87, winRate: 82, avatar: 'https://i.pravatar.cc/150?img=1' },
          { id: 2, username: 'scplanner', score: 23120, scenariosCompleted: 92, winRate: 78, avatar: 'https://i.pravatar.cc/150?img=2' },
          { id: 3, username: 'logisticspro', score: 21890, scenariosCompleted: 76, winRate: 81, avatar: 'https://i.pravatar.cc/150?img=3' },
          { id: 4, username: 'inventoryguru', score: 20560, scenariosCompleted: 68, winRate: 85, avatar: 'https://i.pravatar.cc/150?img=4' },
          { id: 5, username: 'supplyqueen', score: 19870, scenariosCompleted: 72, winRate: 79, avatar: 'https://i.pravatar.cc/150?img=5' },
          { id: 6, username: 'demandwizard', score: 18730, scenariosCompleted: 65, winRate: 76, avatar: 'https://i.pravatar.cc/150?img=6' },
          { id: 7, username: mockProfile?.username || 'johndoe', score: mockProfile?.stats?.averageScore * 10 || 12450, scenariosCompleted: mockProfile?.stats?.scenariosCompleted || 42, winRate: mockProfile?.stats?.winRate || 67, avatar: mockProfile?.avatar, isCurrentUser: true },
          { id: 8, username: 'logisticsninja', score: 12340, scenariosCompleted: 51, winRate: 72, avatar: 'https://i.pravatar.cc/150?img=7' },
          { id: 9, username: 'supplychainnewbie', score: 11890, scenariosCompleted: 48, winRate: 68, avatar: 'https://i.pravatar.cc/150?img=8' },
          { id: 10, username: 'scenthusiast', score: 10980, scenariosCompleted: 43, winRate: 65, avatar: 'https://i.pravatar.cc/150?img=9' },
        ];

        setProfile(mockProfile);
        setLeaderboard(mockLeaderboard);
        setFormData({
          username: mockProfile.username,
          email: mockProfile.email,
          bio: mockProfile.bio,
          avatar: mockProfile.avatar
        });
        setError(null);
      } catch (err) {
        console.error('Failed to fetch profile data:', err);
        setError('Failed to load profile data. Please try again later.');
      } finally {
        setIsLoading(false);
      }
    };

    if (user) {
      fetchData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setIsLoading(true);
      // In a real app, this would be an API call to update the profile
      // await simulationApi.updateProfile(formData);

      // Update local state
      setProfile(prev => ({
        ...prev,
        ...formData
      }));

      // Update auth context
      await updateProfile(formData);

      setIsEditing(false);
    } catch (err) {
      console.error('Failed to update profile:', err);
      setError('Failed to update profile. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAvatarUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // In a real app, you would upload the file to your server
    // and get back a URL to the uploaded image
    // const formData = new FormData();
    // formData.append('avatar', file);
    // const response = await simulationApi.uploadAvatar(formData);

    // For demo purposes, we'll just create a local URL
    const imageUrl = URL.createObjectURL(file);

    setFormData(prev => ({
      ...prev,
      avatar: imageUrl
    }));
  };

  // Loading state
  if (isLoading || !profile) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-7xl mx-auto">
          <div className="animate-pulse space-y-6">
            <Skeleton className="h-8 w-1/4" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="md:col-span-1 space-y-6">
                <Skeleton className="h-96 rounded-lg" />
              </div>
              <div className="md:col-span-2 space-y-6">
                <Skeleton className="h-96 rounded-lg" />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-7xl mx-auto">
          <Alert variant="error">
            {error}
          </Alert>
        </div>
      </div>
    );
  }

  // Format date
  const formatDate = (dateString) => {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(dateString).toLocaleDateString(undefined, options);
  };

  return (
    <div className="min-h-screen bg-background py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="md:flex md:items-center md:justify-between mb-8">
          <div className="flex-1 min-w-0">
            <h2 className="text-2xl font-bold leading-7 text-foreground sm:text-3xl sm:truncate">
              {isEditing ? 'Edit Profile' : 'My Profile'}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {isEditing
                ? 'Update your profile information'
                : 'View and manage your profile, stats, and achievements'}
            </p>
          </div>
          <div className="mt-4 flex md:mt-0 md:ml-4">
            {!isEditing ? (
              <Button
                onClick={() => setIsEditing(true)}
                leftIcon={<Pencil className="h-4 w-4" />}
              >
                Edit Profile
              </Button>
            ) : (
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => {
                    setIsEditing(false);
                    // Reset form data
                    setFormData({
                      username: profile.username,
                      email: profile.email,
                      bio: profile.bio,
                      avatar: profile.avatar
                    });
                  }}
                  leftIcon={<X className="h-4 w-4" />}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleSubmit}
                  loading={isLoading}
                  leftIcon={<Check className="h-4 w-4" />}
                >
                  {isLoading ? 'Saving...' : 'Save Changes'}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onChange={(_, val) => setActiveTab(val)} className="mb-8">
          <TabsList>
            <Tab value="overview">Overview</Tab>
            <Tab value="stats">Statistics</Tab>
            <Tab value="achievements">Achievements</Tab>
            <Tab value="history">Scenario History</Tab>
            <Tab value="leaderboard">Leaderboard</Tab>
          </TabsList>
        </Tabs>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - Profile Card */}
          <div className="lg:col-span-1">
            <Card>
              <CardContent className="pt-6">
                <div className="flex flex-col items-center">
                  <div className="relative">
                    {isEditing ? (
                      <div className="group relative">
                        <img
                          className="h-32 w-32 rounded-full object-cover"
                          src={formData.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(formData.username)}&background=random`}
                          alt=""
                        />
                        <label
                          htmlFor="avatar-upload"
                          className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-full opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                        >
                          <Pencil className="h-6 w-6 text-white" />
                          <input
                            id="avatar-upload"
                            name="avatar-upload"
                            type="file"
                            className="sr-only"
                            accept="image/*"
                            onChange={handleAvatarUpload}
                          />
                        </label>
                      </div>
                    ) : (
                      <img
                        className="h-32 w-32 rounded-full object-cover"
                        src={profile.avatar}
                        alt=""
                      />
                    )}
                  </div>

                  {isEditing ? (
                    <div className="mt-4 w-full space-y-4">
                      <FormField label="Username">
                        <Input
                          type="text"
                          name="username"
                          id="username"
                          value={formData.username}
                          onChange={handleInputChange}
                        />
                      </FormField>
                      <FormField label="Email">
                        <Input
                          type="email"
                          name="email"
                          id="email"
                          value={formData.email}
                          onChange={handleInputChange}
                        />
                      </FormField>
                      <FormField label="Bio">
                        <Textarea
                          id="bio"
                          name="bio"
                          rows="3"
                          value={formData.bio}
                          onChange={handleInputChange}
                        />
                      </FormField>
                    </div>
                  ) : (
                    <div className="text-center mt-4">
                      <h3 className="text-lg font-medium text-foreground">{profile.username}</h3>
                      <p className="mt-1 text-sm text-muted-foreground">{profile.bio}</p>
                      <div className="mt-4 flex items-center justify-center text-sm text-muted-foreground">
                        <Calendar className="flex-shrink-0 mr-1.5 h-5 w-5" />
                        Member since {formatDate(profile.joinDate)}
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>

              {!isEditing && (
                <div className="bg-muted/50 px-4 py-4 sm:px-6 rounded-b-lg">
                  <div className="flex flex-wrap justify-center gap-4">
                    <div className="text-center">
                      <p className="text-sm font-medium text-muted-foreground">Rank</p>
                      <p className="text-lg font-semibold text-foreground">#{profile.stats.rank}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-muted-foreground">Scenarios</p>
                      <p className="text-lg font-semibold text-foreground">{profile.stats.scenariosCompleted}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-muted-foreground">Win Rate</p>
                      <p className="text-lg font-semibold text-foreground">{profile.stats.winRate}%</p>
                    </div>
                  </div>
                </div>
              )}
            </Card>

            {/* Quick Stats */}
            {!isEditing && activeTab !== 'leaderboard' && (
              <Card className="mt-6">
                <CardHeader>
                  <CardTitle>Quick Stats</CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="p-4 bg-muted/50 rounded-lg">
                      <dt className="text-sm font-medium text-muted-foreground truncate">Highest Score</dt>
                      <dd className="mt-1 text-2xl font-semibold text-foreground">1,890</dd>
                    </div>
                    <div className="p-4 bg-muted/50 rounded-lg">
                      <dt className="text-sm font-medium text-muted-foreground truncate">Current Streak</dt>
                      <dd className="mt-1 text-2xl font-semibold text-foreground">{profile.stats.currentStreak} days</dd>
                    </div>
                    <div className="p-4 bg-muted/50 rounded-lg">
                      <dt className="text-sm font-medium text-muted-foreground truncate">Total Play Time</dt>
                      <dd className="mt-1 text-2xl font-semibold text-foreground">{profile.stats.totalPlayTime}</dd>
                    </div>
                    <div className="p-4 bg-muted/50 rounded-lg">
                      <dt className="text-sm font-medium text-muted-foreground truncate">Achievements</dt>
                      <dd className="mt-1 text-2xl font-semibold text-foreground">
                        {profile.achievements.filter(a => a.earned).length}/{profile.achievements.length}
                      </dd>
                    </div>
                  </dl>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Column - Content */}
          <div className="lg:col-span-2">
            {activeTab === 'overview' && !isEditing && (
              <div className="space-y-6">
                {/* Welcome Card */}
                <div className="bg-primary/10 border border-primary/20 rounded-lg p-6">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <User className="h-12 w-12 text-primary" />
                    </div>
                    <div className="ml-4">
                      <h3 className="text-lg font-medium text-primary">Welcome back, {profile.username}!</h3>
                      <div className="mt-2 text-sm text-primary/80">
                        <p>You're currently ranked <span className="font-semibold">#{profile.stats.rank}</span> out of {profile.stats.totalScenarioUsers} users.</p>
                        <p className="mt-1">You've played {profile.stats.scenariosCompleted} games with a {profile.stats.winRate}% win rate.</p>
                      </div>
                      <div className="mt-4">
                        <Button onClick={() => setActiveTab('leaderboard')}>
                          View Leaderboard
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Recent Activity */}
                <Card>
                  <CardHeader className="border-b border-border">
                    <CardTitle>Recent Activity</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <ul className="divide-y divide-border">
                      {profile.recentGames.map((game) => (
                        <li key={game.id} className="px-4 py-4 sm:px-6">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center">
                              <div className="flex-shrink-0">
                                {game.status === 'won' ? (
                                  <Trophy className="h-8 w-8 text-yellow-500" />
                                ) : (
                                  <BarChart3 className="h-8 w-8 text-muted-foreground" />
                                )}
                              </div>
                              <div className="ml-4">
                                <p className="text-sm font-medium text-foreground">
                                  {game.status === 'won' ? 'You won' : 'You played'} <span className="font-semibold">{game.name}</span>
                                </p>
                                <p className="text-sm text-muted-foreground">
                                  Scored {game.score} points - {new Date(game.date).toLocaleDateString()}
                                </p>
                              </div>
                            </div>
                            <div className="ml-4 flex-shrink-0">
                              <Badge variant={game.status === 'won' ? 'success' : 'secondary'}>
                                {game.status === 'won' ? 'Victory' : 'Completed'}
                              </Badge>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                  <div className="bg-muted/50 px-4 py-4 sm:px-6 text-right rounded-b-lg">
                    <button
                      onClick={() => setActiveTab('history')}
                      className="text-sm font-medium text-primary hover:text-primary/80"
                    >
                      View all activity &rarr;
                    </button>
                  </div>
                </Card>

                {/* Next Achievement */}
                <Card>
                  <CardHeader className="border-b border-border">
                    <CardTitle>Next Achievement</CardTitle>
                  </CardHeader>
                  <CardContent className="pt-6">
                    {profile.achievements.find(a => !a.earned) ? (
                      <div className="flex items-start">
                        <div className="flex-shrink-0 bg-yellow-100 dark:bg-yellow-900/30 rounded-full p-3">
                          <Target className="h-6 w-6 text-yellow-600 dark:text-yellow-400" />
                        </div>
                        <div className="ml-4">
                          <h4 className="text-lg font-medium text-foreground">
                            {profile.achievements.find(a => !a.earned).name}
                          </h4>
                          <p className="mt-1 text-sm text-muted-foreground">
                            {profile.achievements.find(a => !a.earned).description}
                          </p>
                          <div className="mt-2 w-full bg-muted rounded-full h-2.5">
                            <div className="bg-yellow-400 h-2.5 rounded-full" style={{ width: '65%' }}></div>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">65% complete</p>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-6">
                        <p className="text-muted-foreground">You've unlocked all available achievements! More coming soon.</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}

            {activeTab === 'stats' && (
              <Card>
                <CardHeader className="border-b border-border">
                  <CardTitle>Scenario Statistics</CardTitle>
                </CardHeader>
                <CardContent className="pt-6">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <h4 className="text-sm font-medium text-muted-foreground">Scenarios Completed</h4>
                      <p className="mt-1 text-3xl font-semibold text-foreground">{profile.stats.scenariosCompleted}</p>
                    </div>
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <h4 className="text-sm font-medium text-muted-foreground">Scenarios Won</h4>
                      <p className="mt-1 text-3xl font-semibold text-foreground">{profile.stats.scenariosWon}</p>
                    </div>
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <h4 className="text-sm font-medium text-muted-foreground">Win Rate</h4>
                      <p className="mt-1 text-3xl font-semibold text-foreground">{profile.stats.winRate}%</p>
                    </div>
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <h4 className="text-sm font-medium text-muted-foreground">Average Score</h4>
                      <p className="mt-1 text-3xl font-semibold text-foreground">{profile.stats.averageScore}</p>
                    </div>
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <h4 className="text-sm font-medium text-muted-foreground">Current Streak</h4>
                      <p className="mt-1 text-3xl font-semibold text-foreground">{profile.stats.currentStreak} days</p>
                    </div>
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <h4 className="text-sm font-medium text-muted-foreground">Highest Streak</h4>
                      <p className="mt-1 text-3xl font-semibold text-foreground">{profile.stats.highestStreak} days</p>
                    </div>
                  </div>

                  <div className="mt-8">
                    <h4 className="text-sm font-medium text-foreground mb-4">Performance Over Time</h4>
                    <div className="bg-muted/50 p-4 rounded-lg h-64 flex items-center justify-center">
                      <p className="text-muted-foreground">Performance chart would be displayed here</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {activeTab === 'achievements' && (
              <Card>
                <CardHeader className="border-b border-border">
                  <CardTitle>Achievements</CardTitle>
                  <CardDescription>
                    {profile.achievements.filter(a => a.earned).length} of {profile.achievements.length} achievements unlocked
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-6">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {profile.achievements.map((achievement) => (
                      <div
                        key={achievement.id}
                        className={cn(
                          'relative rounded-lg border p-4',
                          achievement.earned
                            ? 'border-transparent bg-muted/50'
                            : 'border-border bg-background opacity-50'
                        )}
                      >
                        <div className="flex items-start">
                          <div className={cn(
                            'flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center',
                            achievement.earned ? 'bg-yellow-100 dark:bg-yellow-900/30' : 'bg-muted'
                          )}>
                            <Trophy className={cn(
                              'h-5 w-5',
                              achievement.earned ? 'text-yellow-600 dark:text-yellow-400' : 'text-muted-foreground'
                            )} />
                          </div>
                          <div className="ml-4">
                            <h4 className="text-sm font-medium text-foreground">
                              {achievement.name}
                              {achievement.earned && (
                                <Badge variant="success" size="sm" className="ml-2">
                                  Unlocked
                                </Badge>
                              )}
                            </h4>
                            <p className="mt-1 text-sm text-muted-foreground">{achievement.description}</p>
                            {achievement.earned && achievement.date && (
                              <p className="mt-1 text-xs text-muted-foreground">
                                Unlocked on {new Date(achievement.date).toLocaleDateString()}
                              </p>
                            )}
                          </div>
                        </div>
                        {!achievement.earned && (
                          <div className="absolute inset-0 flex items-center justify-center bg-background/75 rounded-lg">
                            <ShieldCheck className="h-6 w-6 text-muted-foreground" />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {activeTab === 'history' && (
              <Card>
                <CardHeader className="border-b border-border">
                  <div className="flex justify-between items-center">
                    <div>
                      <CardTitle>Scenario History</CardTitle>
                      <CardDescription>Your recent game sessions and results</CardDescription>
                    </div>
                    <Select defaultValue="all" className="w-40">
                      <SelectOption value="week">Last 7 days</SelectOption>
                      <SelectOption value="month">Last 30 days</SelectOption>
                      <SelectOption value="all">All time</SelectOption>
                    </Select>
                  </div>
                </CardHeader>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Scenario</TableHead>
                        <TableHead>Date</TableHead>
                        <TableHead>Score</TableHead>
                        <TableHead>Position</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {profile.recentGames.map((game) => (
                        <TableRow key={game.id} className="hover:bg-muted/50">
                          <TableCell>
                            <div className="text-sm font-medium text-foreground">{game.name}</div>
                            <div className="text-sm text-muted-foreground">{game.id}</div>
                          </TableCell>
                          <TableCell>
                            <div className="text-sm text-foreground">{new Date(game.date).toLocaleDateString()}</div>
                            <div className="text-sm text-muted-foreground">{new Date(game.date).toLocaleTimeString()}</div>
                          </TableCell>
                          <TableCell>
                            <div className="text-sm text-foreground">{game.score}</div>
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                game.position === 1 ? 'warning' :
                                game.position === 2 ? 'secondary' :
                                game.position === 3 ? 'warning' :
                                'info'
                              }
                            >
                              #{game.position}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={game.status === 'won' ? 'success' : 'destructive'}>
                              {game.status === 'won' ? 'Won' : 'Lost'}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
                <div className="bg-muted/50 px-4 py-3 flex items-center justify-between border-t border-border rounded-b-lg">
                  <div className="flex-1 flex justify-between sm:hidden">
                    <Button variant="outline" size="sm">Previous</Button>
                    <Button variant="outline" size="sm">Next</Button>
                  </div>
                  <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">
                        Showing <span className="font-medium">1</span> to <span className="font-medium">5</span> of{' '}
                        <span className="font-medium">{profile.recentGames.length}</span> results
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button variant="outline" size="sm">
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <Button variant="default" size="sm">1</Button>
                      <Button variant="outline" size="sm">2</Button>
                      <Button variant="outline" size="sm">3</Button>
                      <Button variant="outline" size="sm">
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {activeTab === 'leaderboard' && (
              <Card>
                <CardHeader className="border-b border-border">
                  <div className="flex justify-between items-center">
                    <div>
                      <CardTitle>Global Leaderboard</CardTitle>
                      <CardDescription>Top users by total score</CardDescription>
                    </div>
                    <Select defaultValue="global" className="w-40">
                      <SelectOption value="global">Global</SelectOption>
                      <SelectOption value="friends">Friends</SelectOption>
                      <SelectOption value="weekly">This Week</SelectOption>
                      <SelectOption value="monthly">This Month</SelectOption>
                    </Select>
                  </div>
                </CardHeader>
                <CardContent className="p-0">
                  <ul className="divide-y divide-border">
                    {leaderboard.map((scenarioUser, index) => (
                      <li
                        key={user.id}
                        className={cn(
                          'px-4 py-4 sm:px-6',
                          user.isCurrentUser ? 'bg-primary/10' : 'hover:bg-muted/50'
                        )}
                      >
                        <div className="flex items-center">
                          <div className="flex-shrink-0">
                            {index < 3 ? (
                              <div className={cn(
                                'h-8 w-8 rounded-full flex items-center justify-center',
                                index === 0 ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' :
                                index === 1 ? 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200' :
                                'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
                              )}>
                                <span className="font-medium">{index + 1}</span>
                              </div>
                            ) : (
                              <div className="h-8 w-8 rounded-full flex items-center justify-center bg-muted">
                                <span className="text-muted-foreground font-medium">{index + 1}</span>
                              </div>
                            )}
                          </div>
                          <div className="ml-4 flex items-center flex-1 min-w-0">
                            <div className="flex-shrink-0 h-10 w-10">
                              <img
                                className="h-10 w-10 rounded-full"
                                src={user.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(user.username)}&background=random`}
                                alt=""
                              />
                            </div>
                            <div className="ml-4 min-w-0 flex-1">
                              <div className="flex justify-between">
                                <p className={cn(
                                  'text-sm font-medium truncate',
                                  user.isCurrentUser ? 'text-primary' : 'text-foreground'
                                )}>
                                  {user.username}
                                  {user.isCurrentUser && ' (You)'}
                                </p>
                                <div className="ml-2 flex-shrink-0 flex">
                                  <p className="text-sm text-muted-foreground">
                                    {user.score.toLocaleString()} pts
                                  </p>
                                </div>
                              </div>
                              <div className="mt-1 flex justify-between">
                                <p className="text-sm text-muted-foreground">
                                  {user.scenariosCompleted} games - {user.winRate}% win rate
                                </p>
                                {user.isCurrentUser && (
                                  <Badge variant="info">
                                    Your Rank: #{index + 1}
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                        {user.isCurrentUser && index < leaderboard.length - 1 && (
                          <div className="mt-4 pt-4 border-t border-border">
                            <div className="flex justify-between text-sm">
                              <span className="text-muted-foreground">Next rank (#{index}):</span>
                              <span className="font-medium">
                                {Math.ceil((leaderboard[index].score - user.score) / 1000) * 1000 - (leaderboard[index].score - user.score)} pts to go
                              </span>
                            </div>
                            <div className="mt-2 w-full bg-muted rounded-full h-2">
                              <div
                                className="bg-primary h-2 rounded-full"
                                style={{
                                  width: `${((leaderboard[index].score - user.score) / 1000) * 100}%`
                                }}
                              ></div>
                            </div>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </CardContent>
                <div className="bg-muted/50 px-4 py-3 flex items-center justify-between border-t border-border rounded-b-lg">
                  <div className="flex-1 flex justify-between sm:hidden">
                    <Button variant="outline" size="sm">Previous</Button>
                    <Button variant="outline" size="sm">Next</Button>
                  </div>
                  <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">
                        Showing <span className="font-medium">1</span> to <span className="font-medium">10</span> of{' '}
                        <span className="font-medium">{leaderboard.length}</span> results
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button variant="outline" size="sm">
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <Button variant="default" size="sm">1</Button>
                      <Button variant="outline" size="sm">2</Button>
                      <Button variant="outline" size="sm">3</Button>
                      <Button variant="outline" size="sm">
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;
