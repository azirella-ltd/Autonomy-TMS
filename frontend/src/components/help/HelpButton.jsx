import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { useHelp } from '../../contexts/HelpContext';

export const HelpButton = ({ className = '', size = 'md', floating = false }) => {
  const { openHelp } = useHelp();

  const sizeClasses = {
    sm: 'p-1',
    md: 'p-2',
    lg: 'p-3',
  };

  const iconSizes = {
    sm: 'h-5 w-5',
    md: 'h-6 w-6',
    lg: 'h-7 w-7',
  };

  const buttonClasses = `
    ${floating ? 'fixed bottom-6 right-6 z-40 rounded-full shadow-lg' : 'rounded-md'} 
    ${sizeClasses[size] || sizeClasses.md}
    bg-white text-gray-400 hover:text-gray-500 
    focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500
    ${floating ? 'shadow-lg' : ''}
    ${className}
  `;

  return (
    <button
      type="button"
      onClick={openHelp}
      className={buttonClasses}
      aria-label="Help"
    >
      <QuestionMarkCircleIcon className={`${iconSizes[size] || iconSizes.md} text-indigo-600`} aria-hidden="true" />
      {floating && (
        <span className="sr-only">Help</span>
      )}
    </button>
  );
};

export default HelpButton;
