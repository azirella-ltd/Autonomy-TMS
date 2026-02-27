/**
 * CapabilityAwareNavbar Component - Autonomy UI Kit
 *
 * A capability-aware navigation bar that filters menu items based on user permissions.
 * Includes mobile drawer navigation and user profile menu.
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 */

import { useState, useMemo } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import {
  Menu,
  X,
  User,
  Settings,
  LogOut,
  HelpCircle,
  Bell,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Button, IconButton, Badge, Chip, Typography } from './common';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from './ui/sheet';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from './ui/tooltip';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from './ui/collapsible';
import { Avatar, AvatarFallback } from './ui/avatar';
import { cn } from '../lib/utils/cn';
import { useAuth } from '../contexts/AuthContext';
import { useCapabilities } from '../hooks/useCapabilities';
import { isSystemAdmin, isTenantAdmin } from '../utils/authUtils';
import { getFilteredNavigation } from '../config/navigationConfig';

const CapabilityAwareNavbar = () => {
  const { user, isAuthenticated, logout } = useAuth();
  const { hasCapability, loading: capabilitiesLoading } = useCapabilities();
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [expandedSections, setExpandedSections] = useState({});
  const navigate = useNavigate();
  const location = useLocation();

  const isSysAdmin = isSystemAdmin(user);
  const isGrpAdmin = isTenantAdmin(user);

  // Get filtered navigation based on user capabilities
  const navigation = useMemo(() => {
    if (capabilitiesLoading) return [];
    return getFilteredNavigation(hasCapability, isSysAdmin, isGrpAdmin);
  }, [hasCapability, isSysAdmin, isGrpAdmin, capabilitiesLoading]);

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const handleMobileDrawerToggle = () => {
    setMobileDrawerOpen(!mobileDrawerOpen);
  };

  const handleSectionToggle = (sectionName) => {
    setExpandedSections((prev) => ({
      ...prev,
      [sectionName]: !prev[sectionName],
    }));
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

  const isCurrentPath = (path) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  if (!isAuthenticated) {
    return null;
  }

  // Mobile Drawer Content
  const drawerContent = (
    <div className="pt-2">
      <div className="px-4 mb-4 flex items-center">
        <img
          src="/autonomy_logo.svg"
          alt="Autonomy"
          className="h-7 w-auto mr-2"
        />
      </div>
      <hr className="border-border" />
      <nav className="mt-2">
        {navigation.map((section, sectionIndex) => (
          <div key={section.section}>
            {section.divider && sectionIndex > 0 && (
              <hr className="border-border my-2" />
            )}

            {/* Section Header */}
            <Collapsible
              open={expandedSections[section.section]}
              onOpenChange={() => handleSectionToggle(section.section)}
            >
              <CollapsibleTrigger className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 rounded-md transition-colors">
                <span className="text-xs font-bold uppercase text-muted-foreground tracking-wider">
                  {section.section}
                </span>
                {expandedSections[section.section] ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </CollapsibleTrigger>

              {/* Section Items */}
              <CollapsibleContent>
                <div className="py-1">
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const current = isCurrentPath(item.path);
                    const isDisabled = item.disabled || item.comingSoon;

                    return (
                      <TooltipProvider key={item.path}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div>
                              <Link
                                to={isDisabled ? '#' : item.path}
                                onClick={(e) => {
                                  if (isDisabled) {
                                    e.preventDefault();
                                    return;
                                  }
                                  setMobileDrawerOpen(false);
                                }}
                                className={cn(
                                  'flex items-center gap-3 px-4 py-2 pl-8 rounded-md transition-colors',
                                  current && 'bg-accent text-accent-foreground',
                                  !current && !isDisabled && 'hover:bg-muted/50',
                                  isDisabled && 'opacity-40 cursor-not-allowed'
                                )}
                              >
                                <Icon
                                  className={cn(
                                    'h-4 w-4',
                                    current ? 'text-primary' : 'text-muted-foreground'
                                  )}
                                />
                                <span
                                  className={cn(
                                    'text-sm',
                                    current ? 'font-semibold' : 'font-normal'
                                  )}
                                >
                                  {item.label}
                                </span>
                                {item.comingSoon && (
                                  <Chip size="sm" className="ml-auto h-5 text-[10px]">
                                    Soon
                                  </Chip>
                                )}
                              </Link>
                            </div>
                          </TooltipTrigger>
                          {(item.disabled || item.comingSoon) && (
                            <TooltipContent side="right">
                              {item.disabled
                                ? `Requires: ${item.requiredCapability}`
                                : 'Coming Soon'}
                            </TooltipContent>
                          )}
                        </Tooltip>
                      </TooltipProvider>
                    );
                  })}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        ))}
      </nav>
    </div>
  );

  return (
    <>
      {/* AppBar */}
      <header
        className={cn(
          'fixed top-0 left-0 right-0 z-50',
          'bg-white/80 dark:bg-slate-950/80 backdrop-blur-md',
          'shadow-[0_2px_20px_rgba(0,0,0,0.1)]',
          'border-b border-black/5 dark:border-white/5'
        )}
      >
        <div className="flex items-center justify-between h-16 px-4 md:px-8">
          {/* Left side - Logo & Mobile Menu */}
          <div className="flex items-center">
            {/* Mobile Menu Button */}
            <IconButton
              variant="ghost"
              onClick={handleMobileDrawerToggle}
              className="mr-2 md:hidden"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </IconButton>

            <Link
              to={isSysAdmin ? '/admin/tenants' : '/dashboard'}
              className="flex items-center no-underline"
            >
              <img
                src="/autonomy_logo.svg"
                alt="Autonomy"
                className="h-6 w-auto mr-2"
              />
            </Link>
          </div>

          {/* Right side - User menu */}
          <div className="flex items-center gap-1">
            {!isSysAdmin && (
              <>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <IconButton
                        variant="ghost"
                        onClick={() => navigate('/help')}
                        aria-label="Help"
                      >
                        <HelpCircle className="h-5 w-5 text-foreground" />
                      </IconButton>
                    </TooltipTrigger>
                    <TooltipContent>Help</TooltipContent>
                  </Tooltip>
                </TooltipProvider>

                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <IconButton variant="ghost" aria-label="Notifications">
                        <div className="relative">
                          <Bell className="h-5 w-5 text-foreground" />
                          <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-medium text-white">
                            3
                          </span>
                        </div>
                      </IconButton>
                    </TooltipTrigger>
                    <TooltipContent>Notifications</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </>
            )}

            {/* User Menu */}
            <div className="flex items-center ml-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    className="flex items-center gap-2 hover:bg-black/5 dark:hover:bg-white/5"
                  >
                    <Avatar className="h-8 w-8">
                      <AvatarFallback className="bg-primary text-primary-foreground text-sm">
                        {getInitials(user?.name || user?.email || '')}
                      </AvatarFallback>
                    </Avatar>
                    <div className="hidden sm:block text-left ml-1">
                      <p className="text-sm font-medium text-foreground">
                        {user?.name || user?.full_name || user?.email || 'User'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {user?.powell_role ? user.powell_role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : (user?.user_type === 'systemadmin' ? 'System Admin' : user?.user_type === 'tenantadmin' ? 'Organization Admin' : '')}
                      </p>
                    </div>
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem
                    onClick={() => navigate('/profile')}
                    className="cursor-pointer"
                  >
                    <User className="h-4 w-4 mr-2" />
                    Profile
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => navigate('/settings')}
                    className="cursor-pointer"
                  >
                    <Settings className="h-4 w-4 mr-2" />
                    Settings
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={handleLogout}
                    className="cursor-pointer text-destructive focus:text-destructive"
                  >
                    <LogOut className="h-4 w-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Drawer */}
      <Sheet open={mobileDrawerOpen} onOpenChange={setMobileDrawerOpen}>
        <SheetContent side="left" className="w-[280px] p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation Menu</SheetTitle>
          </SheetHeader>
          {drawerContent}
        </SheetContent>
      </Sheet>

      {/* Spacer for fixed AppBar */}
      <div className="h-16" />
    </>
  );
};

export default CapabilityAwareNavbar;
