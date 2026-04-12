/**
 * Common Components - Autonomy UI Kit
 *
 * Export all common UI components for easy imports.
 * Usage: import { Card, Button, Alert } from '../components/common';
 *
 * Components are sourced from either:
 * - @azirella-ltd/autonomy-frontend (shared package — preferred)
 * - Local ./ComponentName.jsx (TMS-specific or not yet in package)
 *
 * When the package ships an enhanced version, swap the re-export
 * source and delete the local file. See CONSUMER_ADOPTION_LOG.md.
 */

// Card components — from shared package (v1.2.0+)
export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@azirella-ltd/autonomy-frontend';

// Button components — from shared package (v1.3.0+)
export { Button, IconButton } from '@azirella-ltd/autonomy-frontend';

// Alert components
export { Alert, AlertTitle, AlertDescription } from './Alert';

// Badge components
export { Badge, Chip } from './Badge';

// Input components
export { Input, Label, FormField, Textarea } from './Input';

// Loading components
export {
  Spinner,
  LoadingOverlay,
  FullPageLoader,
  Skeleton,
  CircularProgress,
} from './Loading';

// Typography components
export {
  Typography,
  H1,
  H2,
  H3,
  H4,
  H5,
  H6,
  Text,
  SmallText,
  Caption,
} from './Typography';

// Table components
export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
  TableContainer,
} from './Table';

// Modal components
export {
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  ModalDescription,
} from './Modal';

// Select components
export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectLabel,
  SelectItem,
  SelectSeparator,
  SelectScrollUpButton,
  SelectScrollDownButton,
  SelectOption,
  NativeSelect,
} from './Select';

// Slider components
export {
  Slider,
  SliderTrack,
  SliderFilledTrack,
  SliderThumb,
} from './Slider';

// Toast components
export { ToastProvider, useToast } from './Toast';

// Tabs components
export { Tabs, TabsList, Tab, TabPanel, TabsTrigger, TabsContent } from './Tabs';

// ToggleGroup components
export { ToggleGroup, ToggleGroupItem } from './ToggleGroup';

// Dialog components
export {
  Dialog,
  DialogTrigger,
  DialogPortal,
  DialogClose,
  DialogOverlay,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from './Dialog';

// Accordion components
export {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from './Accordion';

// Separator component
export { Separator } from './Separator';

// ScrollArea components
export { ScrollArea, ScrollBar } from './ScrollArea';

// Switch component
export { Switch } from './Switch';

// RadioGroup components
export { RadioGroup, RadioGroupItem } from './RadioGroup';

// Checkbox component
export { Checkbox } from './Checkbox';

// Popover components
export { Popover, PopoverTrigger, PopoverContent } from './Popover';

// HoverCard components
export { HoverCard, HoverCardTrigger, HoverCardContent } from './HoverCard';

// Progress components
export { Progress } from './Progress';

// Tooltip components
export {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from './Tooltip';

// Avatar components
export { Avatar, AvatarImage, AvatarFallback } from './Avatar';

// DropdownMenu components
export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuGroup,
  DropdownMenuPortal,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuRadioGroup,
} from './DropdownMenu';

// Collapsible components
export {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from './Collapsible';

// Sheet components
export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
  SheetPortal,
  SheetOverlay,
} from './Sheet';
