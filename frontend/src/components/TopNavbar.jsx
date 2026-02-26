/**
 * TopNavbar - Autonomy UI Kit Version
 *
 * Top navigation bar using Tailwind CSS and lucide-react icons.
 * Provides user menu, notifications, and context breadcrumbs.
 */

import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useLocation, useParams } from 'react-router-dom';
import {
  Menu,
  X,
  User,
  Settings,
  LogOut,
  HelpCircle,
  Bell,
  Shield,
  GraduationCap,
  Brain,
  Users,
  Network,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { isSystemAdmin } from '../utils/authUtils';
import simulationApi from '../services/api';
import { getSupplyChainConfigById } from '../services/supplyChainConfigService';
import { cn } from '../lib/utils/cn';

const TopNavbar = ({ sidebarOpen = true }) => {
  const { user, isAuthenticated, logout } = useAuth();
  const [currentPath, setCurrentPath] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [gameInfo, setGameInfo] = useState(null);
  const [systemConfigName, setSystemConfigName] = useState(null);
  const [supplyChainConfigName, setSupplyChainConfigName] = useState(null);
  const menuRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const { gameId, id: routeId, configId } = params;
  const supplyChainConfigId = routeId || configId || null;

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Update current path when location changes
  useEffect(() => {
    setCurrentPath(location.pathname);
  }, [location]);

  // Load system config name
  useEffect(() => {
    let isMounted = true;

    const loadSystemConfigName = async () => {
      try {
        const data = await simulationApi.getSystemConfig();
        if (isMounted) {
          setSystemConfigName(data?.name || null);
        }
      } catch (error) {
        if (!isMounted) return;

        let cachedName = null;
        try {
          const cached = localStorage.getItem('systemConfigRanges');
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

    const shouldFetch = systemConfigName === null || location.pathname.includes('system-config');
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
          console.error('Failed to load game info', err);
        }
      } else {
        setGameInfo(null);
      }
    };
    fetchGameInfo();
  }, [gameId]);

  // Load supply chain config name
  useEffect(() => {
    const onSupplyChainRoute = location.pathname.includes('/supply-chain-config');
    const onCustomerSupplyChainRoute = location.pathname.includes('/admin/tenant/supply-chain-configs');
    const onGameFromConfigRoute = location.pathname.includes('/scenarios/new-from-config');

    if (!(onSupplyChainRoute || onCustomerSupplyChainRoute || onGameFromConfigRoute)) {
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

  const handleLogout = async () => {
    try {
      await logout();
      setMenuOpen(false);
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const getInitials = (name) => {
    if (!name) return '';
    return name
      .split(' ')
      .map((part) => part[0])
      .join('')
      .toUpperCase()
      .substring(0, 2);
  };

  const groupName = user?.group?.name || gameInfo?.group?.name;
  const gameConfigName = gameInfo?.config?.name;
  const scDisplayName = supplyChainConfigName || gameConfigName || systemConfigName;
  const gameName = gameInfo?.name;
  const onSystemAdminPage = location.pathname.startsWith('/system');
  const shouldShowContext = !onSystemAdminPage && (groupName || scDisplayName || gameName);

  const contextParts = [];
  if (groupName) contextParts.push(`Group: ${groupName}`);
  if (scDisplayName) contextParts.push(`Config: ${scDisplayName}`);
  if (gameName) contextParts.push(`Game: ${gameName}`);

  if (!isAuthenticated) {
    return null;
  }

  const menuItems = [
    { label: 'Profile', icon: User, path: '/profile' },
    { label: 'Settings', icon: Settings, path: '/settings' },
  ];

  const adminMenuItems = isSysAdmin ? [
    { label: 'Admin Dashboard', icon: Shield, path: '/admin' },
    { label: 'TRM Model Training', icon: GraduationCap, path: '/admin/trm' },
    { label: 'GNN Model Training', icon: Brain, path: '/admin/gnn' },
    { label: 'Organizations', icon: Users, path: '/admin/tenants' },
    { label: 'Supply Chain Configs', icon: Network, path: '/system/supply-chain-configs' },
  ] : [];

  return (
    <header
      className={cn(
        "fixed top-0 right-0 z-30 h-16 bg-background/80 backdrop-blur-md border-b border-border shadow-sm transition-all duration-200 ease-in-out",
        sidebarOpen ? "left-[280px]" : "left-16"
      )}
    >
      <div className="flex items-center justify-between h-full px-4 md:px-6">
        {/* Left side - Logo & Context */}
        <div className="flex items-center gap-4">
          <Link
            to={isSysAdmin ? '/admin/tenants' : '/dashboard'}
            className="flex items-center gap-2 font-medium hover:opacity-80 transition-opacity"
          >
            <img
              src="/autonomy_logo.svg"
              alt="Autonomy"
              className="h-7 w-auto"
            />
          </Link>

          {shouldShowContext && (
            <span className="hidden md:block text-sm text-muted-foreground ml-4">
              {contextParts.join(' | ')}
            </span>
          )}
        </div>

        {/* Right side - Actions & User Menu */}
        <div className="flex items-center gap-2">
          {!isSysAdmin && (
            <>
              <button
                onClick={() => navigate('/help')}
                className="p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                title="Help"
              >
                <HelpCircle className="h-5 w-5" />
              </button>
              <button
                className="relative p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                title="Notifications"
              >
                <Bell className="h-5 w-5" />
                <span className="absolute top-1 right-1 h-2 w-2 bg-destructive rounded-full" />
              </button>
            </>
          )}

          {/* User Menu */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-accent transition-colors"
            >
              <div className="h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium">
                {getInitials(user?.name || '')}
              </div>
              <div className="hidden sm:block text-left mr-1">
                <p className="text-sm font-medium text-foreground">{user?.name || user?.full_name || 'User'}</p>
                <p className="text-xs text-muted-foreground">{user?.powell_role ? user.powell_role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : (user?.user_type === 'systemadmin' ? 'System Admin' : (user?.user_type === 'tenantadmin' || user?.user_type === 'groupadmin') ? 'Organization Admin' : '')}</p>
              </div>
              {menuOpen ? (
                <X className="h-4 w-4 text-muted-foreground" />
              ) : (
                <Menu className="h-4 w-4 text-muted-foreground" />
              )}
            </button>

            {/* Dropdown Menu */}
            {menuOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-popover border border-border rounded-lg shadow-lg py-1 z-50">
                {menuItems.map((item) => (
                  <button
                    key={item.path}
                    onClick={() => {
                      navigate(item.path);
                      setMenuOpen(false);
                    }}
                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-popover-foreground hover:bg-accent transition-colors"
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </button>
                ))}

                {adminMenuItems.length > 0 && (
                  <>
                    <div className="my-1 border-t border-border" />
                    {adminMenuItems.map((item) => (
                      <button
                        key={item.path}
                        onClick={() => {
                          navigate(item.path);
                          setMenuOpen(false);
                        }}
                        className="w-full flex items-center gap-3 px-4 py-2 text-sm text-popover-foreground hover:bg-accent transition-colors"
                      >
                        <item.icon className="h-4 w-4" />
                        {item.label}
                      </button>
                    ))}
                  </>
                )}

                <div className="my-1 border-t border-border" />
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-destructive hover:bg-accent transition-colors"
                >
                  <LogOut className="h-4 w-4" />
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default TopNavbar;
