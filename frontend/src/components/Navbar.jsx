/**
 * Navbar Component
 *
 * Main navigation bar with user menu, context display, and navigation links.
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 */

import { useState, useEffect, useRef } from "react";
import { Link, useNavigate, useLocation, useParams } from "react-router-dom";
import { Button, IconButton, Badge } from "./common";
import {
  Menu as MenuIcon,
  X as CloseIcon,
  User as PersonIcon,
  Settings as SettingsIcon,
  LogOut as LogoutIcon,
  LayoutDashboard as DashboardIcon,
  Gamepad2 as GamesIcon,
  Users as PlayersIcon,
  HelpCircle as HelpIcon,
  Bell as NotificationsIcon,
  BarChart3 as AnalyticsIcon,
  GraduationCap as TrainingIcon,
  Cpu as ModelIcon,
  ShieldCheck as AdminIcon,
  GitBranch as NetworkIcon,
  UsersRound as UsersIcon,
  Lightbulb as InsightsIcon,
  Calendar as PlanningIcon,
  Database as DataIcon,
  Building2 as GroupsIcon,
} from "lucide-react";
import { cn } from "../lib/utils/cn";
import { useAuth } from "../contexts/AuthContext";
import { isSystemAdmin, isGroupAdmin } from "../utils/authUtils";
import simulationApi, { api } from "../services/api";
import { getSupplyChainConfigById } from "../services/supplyChainConfigService";

const Navbar = () => {
  const { user, isAuthenticated, logout } = useAuth();
  const [currentPath, setCurrentPath] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [gameInfo, setGameInfo] = useState(null);
  const [systemConfigName, setSystemConfigName] = useState(null);
  const [supplyChainConfigName, setSupplyChainConfigName] = useState(null);
  const [groupMode, setGroupMode] = useState(null); // 'learning' or 'production'
  const menuRef = useRef(null);
  const buttonRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const { gameId, id: routeId, configId } = params;
  const supplyChainConfigId = routeId || configId || null;

  // Update current path when location changes
  useEffect(() => {
    setCurrentPath(location.pathname);
  }, [location]);

  // Fetch group mode for GROUP_ADMIN users
  useEffect(() => {
    const fetchGroupMode = async () => {
      if (user?.user_type === 'GROUP_ADMIN' && user?.group_id) {
        try {
          const response = await api.get(`/groups/${user.group_id}`);
          setGroupMode(response.data.mode || 'learning');
        } catch (error) {
          console.error('Failed to fetch group mode:', error);
          setGroupMode('learning'); // Default to learning on error
        }
      } else if (user?.user_type === 'SYSTEM_ADMIN') {
        setGroupMode(null); // System admin doesn't have a group mode
      }
    };

    if (user) {
      fetchGroupMode();
    }
  }, [user]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(event.target) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target)
      ) {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    const loadSystemConfigName = async () => {
      try {
        const data = await simulationApi.getSystemConfig();
        if (isMounted) {
          setSystemConfigName(data?.name || null);
        }
      } catch (error) {
        if (!isMounted) {
          return;
        }

        let cachedName = null;
        try {
          const cached = localStorage.getItem("systemConfigRanges");
          if (cached) {
            const parsed = JSON.parse(cached);
            cachedName = parsed?.name || null;
          }
        } catch (_) {
          cachedName = null;
        }

        setSystemConfigName(cachedName);
      }
    };

    const shouldFetch =
      systemConfigName === null || location.pathname.includes("system-config");
    if (shouldFetch) {
      loadSystemConfigName();
    }

    return () => {
      isMounted = false;
    };
  }, [location.pathname, systemConfigName]);

  // Load game information when on a game page
  useEffect(() => {
    const fetchGameInfo = async () => {
      if (gameId) {
        try {
          const data = await simulationApi.getGame(gameId);
          setGameInfo(data);
        } catch (err) {
          console.error("Failed to load game info", err);
        }
      } else {
        setGameInfo(null);
      }
    };
    fetchGameInfo();
  }, [gameId]);

  useEffect(() => {
    const onSupplyChainRoute = location.pathname.includes(
      "/supply-chain-config"
    );
    const onGroupSupplyChainRoute = location.pathname.includes(
      "/admin/group/supply-chain-configs"
    );
    const onGameFromConfigRoute = location.pathname.includes(
      "/scenarios/new-from-config"
    );

    if (
      !(onSupplyChainRoute || onGroupSupplyChainRoute || onGameFromConfigRoute)
    ) {
      setSupplyChainConfigName(null);
      return;
    }

    if (!supplyChainConfigId) {
      setSupplyChainConfigName(null);
      return;
    }

    let isMounted = true;

    const loadSupplyChainConfigName = async () => {
      try {
        const config = await getSupplyChainConfigById(supplyChainConfigId);
        if (isMounted) {
          setSupplyChainConfigName(config?.name || null);
        }
      } catch (error) {
        if (isMounted) {
          setSupplyChainConfigName(null);
        }
      }
    };

    loadSupplyChainConfigName();

    return () => {
      isMounted = false;
    };
  }, [supplyChainConfigId, location.pathname]);

  const isSysAdmin = isSystemAdmin(user);
  // Check for GROUP_ADMIN specifically (not SYSTEM_ADMIN)
  const isGrpAdmin = !isSysAdmin && isGroupAdmin(user);
  const isProductionMode = groupMode === 'production';
  const isLearningMode = groupMode === 'learning';

  // Build navigation based on role and group mode
  const getNavigation = () => {
    if (isSysAdmin) {
      // System Admin: No main navigation, uses dropdown menu
      return [];
    }

    if (isGrpAdmin && isProductionMode) {
      // GROUP_ADMIN (Production): Insights-driven navigation
      return [
        { name: "Insights", path: "/insights", icon: InsightsIcon },
        { name: "Planning", path: "/planning", icon: PlanningIcon },
        { name: "Analytics", path: "/analytics", icon: AnalyticsIcon },
        { name: "AI Agents", path: "/admin/powell", icon: NetworkIcon },
      ];
    }

    if (isGrpAdmin && isLearningMode) {
      // GROUP_ADMIN (Learning): Learning-focused navigation
      return [
        { name: "Dashboard", path: "/admin", icon: DashboardIcon },
        { name: "Scenarios", path: "/games", icon: GamesIcon },
        { name: "ScenarioUsers", path: "/scenarioUsers", icon: PlayersIcon },
        { name: "Analytics", path: "/analytics", icon: AnalyticsIcon },
      ];
    }

    // USER or default: Standard user navigation
    return [
      { name: "Dashboard", path: "/dashboard", icon: DashboardIcon },
      { name: "Games", path: "/games", icon: GamesIcon },
      { name: "ScenarioUsers", path: "/scenarioUsers", icon: PlayersIcon },
      { name: "Analytics", path: "/analytics", icon: AnalyticsIcon },
    ];
  };

  const navigation = getNavigation();

  const handleMenuToggle = () => {
    setMenuOpen(!menuOpen);
  };

  const handleMenuClose = () => {
    setMenuOpen(false);
  };

  const handleLogout = async () => {
    try {
      await logout();
      handleMenuClose();
      navigate("/login");
    } catch (error) {
      console.error("Logout error:", error);
    }
  };

  const getInitials = (name) => {
    if (!name) return "";
    return name
      .split(" ")
      .map((part) => part[0])
      .join("")
      .toUpperCase()
      .substring(0, 2);
  };

  const groupName = user?.group?.name || gameInfo?.group?.name;
  const gameConfigName = gameInfo?.config?.name;
  const scDisplayName =
    supplyChainConfigName || gameConfigName || systemConfigName;
  const gameName = gameInfo?.name;
  const onSystemAdminPage = location.pathname.startsWith("/system");
  const shouldShowContext =
    !onSystemAdminPage && (groupName || scDisplayName || gameName);

  const contextParts = [];
  if (groupName) {
    contextParts.push(`Group: ${groupName}`);
  }
  if (scDisplayName) {
    contextParts.push(`Config: ${scDisplayName}`);
  }
  if (gameName) {
    contextParts.push(`Game: ${gameName}`);
  }

  if (!isAuthenticated) {
    return null; // Don't show navbar for unauthenticated users
  }

  const menuItems = [
    {
      label: "Profile",
      icon: PersonIcon,
      onClick: () => {
        navigate("/profile");
        handleMenuClose();
      },
    },
    {
      label: "Settings",
      icon: SettingsIcon,
      onClick: () => {
        navigate("/settings");
        handleMenuClose();
      },
    },
  ];

  // Build admin menu items based on role and group mode
  const getAdminMenuItems = () => {
    if (isSysAdmin) {
      // SYSTEM_ADMIN: Group management and system-wide configuration
      return [
        {
          label: "Groups Management",
          icon: GroupsIcon,
          onClick: () => {
            navigate("/admin/groups");
            handleMenuClose();
          },
        },
        {
          label: "Synthetic Data Wizard",
          icon: DataIcon,
          onClick: () => {
            navigate("/admin/synthetic-data");
            handleMenuClose();
          },
        },
        {
          label: "Supply Chain Configs",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/system/supply-chain-configs");
            handleMenuClose();
          },
        },
        {
          label: "System Settings",
          icon: AdminIcon,
          onClick: () => {
            navigate("/system/settings");
            handleMenuClose();
          },
        },
      ];
    }

    if (isGrpAdmin && isLearningMode) {
      // GROUP_ADMIN (Learning): Learning-focused admin menu
      return [
        {
          label: "Learning Home",
          icon: AdminIcon,
          onClick: () => {
            navigate("/admin");
            handleMenuClose();
          },
        },
        {
          label: "TRM Model Training",
          icon: TrainingIcon,
          onClick: () => {
            navigate("/admin/trm");
            handleMenuClose();
          },
        },
        {
          label: "GNN Model Training",
          icon: ModelIcon,
          onClick: () => {
            navigate("/admin/gnn");
            handleMenuClose();
          },
        },
        {
          label: "Powell Framework",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/admin/powell");
            handleMenuClose();
          },
        },
        {
          label: "Supply Chain Configs",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/admin/group/supply-chain-configs");
            handleMenuClose();
          },
        },
        {
          label: "SAP Data Management",
          icon: DataIcon,
          onClick: () => {
            navigate("/admin/sap-data");
            handleMenuClose();
          },
        },
        {
          label: "SAP Config Builder",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/deployment/sap-config-builder");
            handleMenuClose();
          },
        },
        {
          label: "Hive Dashboard",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/admin/hive");
            handleMenuClose();
          },
        },
        {
          label: "Authorization Protocol",
          icon: AdminIcon,
          onClick: () => {
            navigate("/admin/authorization-protocol");
            handleMenuClose();
          },
        },
      ];
    }

    if (isGrpAdmin && isProductionMode) {
      // GROUP_ADMIN (Production): Operations-focused admin menu with model training access
      return [
        {
          label: "Insights & Actions",
          icon: InsightsIcon,
          onClick: () => {
            navigate("/insights");
            handleMenuClose();
          },
        },
        {
          label: "TRM Model Training",
          icon: TrainingIcon,
          onClick: () => {
            navigate("/admin/trm");
            handleMenuClose();
          },
        },
        {
          label: "GNN Model Training",
          icon: ModelIcon,
          onClick: () => {
            navigate("/admin/gnn");
            handleMenuClose();
          },
        },
        {
          label: "Powell Framework",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/admin/powell");
            handleMenuClose();
          },
        },
        {
          label: "Hive Dashboard",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/admin/hive");
            handleMenuClose();
          },
        },
        {
          label: "Authorization Protocol",
          icon: AdminIcon,
          onClick: () => {
            navigate("/admin/authorization-protocol");
            handleMenuClose();
          },
        },
        {
          label: "Supply Chain Configs",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/admin/group/supply-chain-configs");
            handleMenuClose();
          },
        },
        {
          label: "SAP Data Management",
          icon: DataIcon,
          onClick: () => {
            navigate("/admin/sap-data");
            handleMenuClose();
          },
        },
        {
          label: "SAP Config Builder",
          icon: NetworkIcon,
          onClick: () => {
            navigate("/deployment/sap-config-builder");
            handleMenuClose();
          },
        },
        {
          label: "User Management",
          icon: UsersIcon,
          onClick: () => {
            navigate("/admin/users");
            handleMenuClose();
          },
        },
      ];
    }

    // Default: no admin menu items for non-admin users
    return [];
  };

  const adminMenuItems = getAdminMenuItems();

  return (
    <header
      className={cn(
        "fixed top-0 left-0 right-0 z-50",
        "bg-white/80 dark:bg-gray-900/80 backdrop-blur-md",
        "shadow-[0_2px_20px_rgba(0,0,0,0.1)]",
        "border-b border-black/5 dark:border-white/5"
      )}
    >
      <div className="flex items-center justify-between px-4 md:px-8 h-16">
        {/* Left side - Logo */}
        <div className="flex items-center">
          <Link
            to={
              isSysAdmin
                ? "/admin/groups"
                : isGrpAdmin && isProductionMode
                ? "/insights"
                : isGrpAdmin && isLearningMode
                ? "/admin"
                : "/dashboard"
            }
            className="flex items-center font-medium no-underline mr-8"
          >
            <img
              src="/autonomy_logo.svg"
              alt="Autonomy"
              className="h-7 w-auto mr-1.5"
            />
          </Link>

          {shouldShowContext && (
            <span className="ml-4 text-sm text-muted-foreground hidden sm:inline">
              {contextParts.join(" | ")}
            </span>
          )}

          {/* Navigation Links - Desktop */}
          {navigation.length > 0 && (
            <nav className="hidden md:flex items-center gap-1 ml-4">
              {navigation.map((item) => {
                const Icon = item.icon;
                return (
                  <Button
                    key={item.name}
                    as={Link}
                    to={item.path}
                    variant="ghost"
                    size="sm"
                    leftIcon={<Icon className="h-4 w-4" />}
                    className={cn(
                      currentPath === item.path
                        ? "text-primary font-semibold"
                        : "text-muted-foreground font-normal"
                    )}
                  >
                    {item.name}
                  </Button>
                );
              })}
            </nav>
          )}
        </div>

        {/* Right side - User menu */}
        <div className="flex items-center gap-1">
          {!isSysAdmin && (
            <>
              <IconButton
                onClick={() => navigate("/help")}
                className="text-muted-foreground hover:text-foreground"
                title="Help"
              >
                <HelpIcon className="h-5 w-5" />
              </IconButton>
              <div className="relative">
                <IconButton
                  className="text-muted-foreground hover:text-foreground"
                  title="Notifications"
                >
                  <NotificationsIcon className="h-5 w-5" />
                </IconButton>
                <Badge
                  variant="destructive"
                  size="sm"
                  className="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 text-xs"
                >
                  3
                </Badge>
              </div>
            </>
          )}

          {/* User Menu */}
          <div className="relative ml-2">
            <button
              ref={buttonRef}
              onClick={handleMenuToggle}
              className={cn(
                "flex items-center gap-2 px-2 py-1.5 rounded-md",
                "text-foreground hover:bg-black/5 dark:hover:bg-white/5",
                "transition-colors"
              )}
            >
              <div
                className={cn(
                  "h-8 w-8 rounded-full flex items-center justify-center",
                  "bg-primary text-primary-foreground text-sm font-medium"
                )}
              >
                {getInitials(user?.name || "")}
              </div>
              <div className="hidden sm:block text-left ml-1">
                <p className="text-sm font-medium leading-tight">
                  {user?.name || user?.full_name || "User"}
                </p>
                <p className="text-xs text-muted-foreground leading-tight">
                  {user?.powell_role ? user.powell_role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : (user?.user_type === 'systemadmin' ? 'System Admin' : user?.user_type === 'groupadmin' ? 'Group Admin' : '')}
                </p>
              </div>
              {menuOpen ? (
                <CloseIcon className="h-4 w-4 text-muted-foreground" />
              ) : (
                <MenuIcon className="h-4 w-4 text-muted-foreground" />
              )}
            </button>

            {/* User Menu Dropdown */}
            {menuOpen && (
              <div
                ref={menuRef}
                className={cn(
                  "absolute right-0 top-full mt-2 w-56 z-50",
                  "bg-white dark:bg-gray-900 rounded-lg",
                  "shadow-lg border border-border",
                  "overflow-hidden"
                )}
              >
                {/* Arrow */}
                <div
                  className={cn(
                    "absolute -top-2 right-4 w-4 h-4",
                    "bg-white dark:bg-gray-900 border-l border-t border-border",
                    "rotate-45 transform"
                  )}
                />

                <div className="py-1 relative">
                  {menuItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.label}
                        onClick={item.onClick}
                        className={cn(
                          "w-full px-4 py-2 flex items-center gap-3",
                          "text-sm text-foreground hover:bg-muted/50",
                          "transition-colors"
                        )}
                      >
                        <Icon className="h-4 w-4 text-muted-foreground" />
                        {item.label}
                      </button>
                    );
                  })}

                  {adminMenuItems.length > 0 && (
                    <>
                      <hr className="my-1 border-border" />
                      {adminMenuItems.map((item) => {
                        const Icon = item.icon;
                        return (
                          <button
                            key={item.label}
                            onClick={item.onClick}
                            className={cn(
                              "w-full px-4 py-2 flex items-center gap-3",
                              "text-sm text-foreground hover:bg-muted/50",
                              "transition-colors"
                            )}
                          >
                            <Icon className="h-4 w-4 text-muted-foreground" />
                            {item.label}
                          </button>
                        );
                      })}
                    </>
                  )}

                  <hr className="my-1 border-border" />
                  <button
                    onClick={handleLogout}
                    className={cn(
                      "w-full px-4 py-2 flex items-center gap-3",
                      "text-sm text-destructive hover:bg-destructive/10",
                      "transition-colors"
                    )}
                  >
                    <LogoutIcon className="h-4 w-4" />
                    Logout
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile Navigation */}
      {navigation.length > 0 && (
        <div className="flex md:hidden border-t border-border">
          {navigation.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                to={item.path}
                className={cn(
                  "flex-1 flex items-center justify-center py-3",
                  "text-muted-foreground hover:text-foreground",
                  currentPath === item.path && [
                    "text-primary",
                    "border-b-2 border-primary",
                  ]
                )}
              >
                <Icon className="h-5 w-5" />
              </Link>
            );
          })}
        </div>
      )}
    </header>
  );
};

export default Navbar;
