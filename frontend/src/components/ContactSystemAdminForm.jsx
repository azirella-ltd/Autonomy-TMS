import { useState } from 'react';

const DEFAULT_SYSTEMADMIN_EMAIL = 'systemadmin@autonomy.ai';

const ContactSystemAdminForm = ({ email, systemAdminEmail = DEFAULT_SYSTEMADMIN_EMAIL, onClose }) => {
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const contactEmail = systemAdminEmail || DEFAULT_SYSTEMADMIN_EMAIL;

  const handleSubmit = (event) => {
    event.preventDefault();

    const lines = [];
    lines.push('Hello System Administrator,');

    if (name.trim()) {
      lines.push(`My name is ${name.trim()}.`);
    }

    lines.push('I tried to sign in to the Autonomy platform but do not have login credentials yet.');

    if (email) {
      lines.push(`Attempted login email: ${email}`);
    }

    if (notes.trim()) {
      lines.push('', notes.trim());
    }

    lines.push('', 'Could you please help me get set up with the correct access credentials?', '', 'Thank you!');

    const subject = 'Access request for Autonomy';
    const body = encodeURIComponent(lines.join('\n'));

    if (typeof window !== 'undefined') {
      window.location.href = `mailto:${contactEmail}?subject=${encodeURIComponent(subject)}&body=${body}`;
    }

    if (onClose) {
      onClose();
    }
  };

  return (
    <div className="mt-6 rounded-lg border border-indigo-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Request access from your system administrator</h3>
          <p className="mt-2 text-sm text-gray-600">
            We couldn't find an account associated with{' '}
            <span className="font-medium text-gray-900">{email || 'your email address'}</span>. Fill out the form below to
            send a quick request for login credentials.
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="ml-4 text-sm font-medium text-indigo-600 hover:text-indigo-500"
          >
            Close
          </button>
        )}
      </div>

      <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="contact-name" className="block text-sm font-medium text-gray-700">
            Your name
          </label>
          <input
            id="contact-name"
            name="name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Jane Doe"
          />
        </div>

        <div>
          <label htmlFor="contact-notes" className="block text-sm font-medium text-gray-700">
            Message to your system administrator (optional)
          </label>
          <textarea
            id="contact-notes"
            name="notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={4}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Let your system administrator know how they can help."
          />
        </div>

        <button
          type="submit"
          className="w-full rounded-md border border-transparent bg-indigo-600 py-2 px-4 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          Open email to system administrator
        </button>
      </form>

      <p className="mt-4 text-xs text-gray-500">
        Prefer to reach out another way? Contact your system administrator directly at{' '}
        <a className="font-medium text-indigo-600 hover:text-indigo-500" href={`mailto:${contactEmail}`}>
          {contactEmail}
        </a>
        .
      </p>
    </div>
  );
};

export default ContactSystemAdminForm;
