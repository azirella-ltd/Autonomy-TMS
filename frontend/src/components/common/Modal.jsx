/**
 * Modal Component - Autonomy UI Kit Wrapper
 *
 * Dialog/Modal component with Chakra-like API.
 * Wraps Radix Dialog for easy migration from Chakra UI Modal.
 */

import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from './Dialog';
import { cn } from '../../lib/utils/cn';

export const Modal = ({
  isOpen,
  onClose,
  children,
  title,
  footer,
  size = 'md',
  closeOnOverlayClick = true,
  closeOnEsc = true,
  className,
  ...props
}) => {
  const sizes = {
    xs: 'max-w-xs',
    sm: 'max-w-sm',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    full: 'max-w-[95vw]',
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && onClose) onClose();
      }}
      {...props}
    >
      <DialogContent
        className={cn(sizes[size], 'max-h-[85vh] flex flex-col', className)}
        onEscapeKeyDown={(e) => {
          if (!closeOnEsc) e.preventDefault();
        }}
        onPointerDownOutside={(e) => {
          if (!closeOnOverlayClick) e.preventDefault();
        }}
        onInteractOutside={(e) => {
          if (!closeOnOverlayClick) e.preventDefault();
        }}
      >
        {title && (
          <DialogHeader className="flex-shrink-0">
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
        )}
        <div className="flex-1 overflow-y-auto min-h-0">
          {children}
        </div>
        {footer && (
          <DialogFooter className="flex-shrink-0">{footer}</DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
};

export const ModalHeader = ({ children, className, ...props }) => (
  <DialogHeader className={className} {...props}>
    {children}
  </DialogHeader>
);

export const ModalTitle = ({ children, className, ...props }) => (
  <DialogTitle className={className} {...props}>
    {children}
  </DialogTitle>
);

export const ModalBody = ({ children, className, ...props }) => (
  <div className={cn('py-4', className)} {...props}>
    {children}
  </div>
);

export const ModalFooter = ({ children, className, ...props }) => (
  <DialogFooter className={className} {...props}>
    {children}
  </DialogFooter>
);

export const ModalDescription = ({ children, className, ...props }) => (
  <DialogDescription className={className} {...props}>
    {children}
  </DialogDescription>
);

export default Modal;
