import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import simulationApi from '../services/api';
import { toast } from 'react-toastify';

const MFASetup = () => {
  const [step, setStep] = useState(1); // 1: Show QR code, 2: Verify code
  const [qrCodeUrl, setQrCodeUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  // Fetch MFA setup data when component mounts
  useEffect(() => {
    const setupMFA = async () => {
      try {
        setIsLoading(true);
        const data = await simulationApi.setupMFA();
        setQrCodeUrl(data.qr_code_url);
        setSecret(data.secret);
        setError('');
      } catch (err) {
        console.error('Failed to load MFA setup:', err);
        toast.error('Failed to load MFA setup. Please try again.');
        navigate('/profile');
      } finally {
        setIsLoading(false);
      }
    };

    setupMFA();
  }, [navigate]);

  const handleVerifyCode = async (e) => {
    e.preventDefault();
    
    if (!verificationCode || verificationCode.length !== 6) {
      setError('Please enter a valid 6-digit code');
      return;
    }
    
    try {
      setIsSubmitting(true);
      const result = await simulationApi.verifyMFA({
        code: verificationCode,
        secret: secret
      });
      
      if (result.recovery_codes) {
        setRecoveryCodes(result.recovery_codes);
        setStep(3); // Show recovery codes
      } else {
        toast.success('Two-factor authentication has been enabled');
        navigate('/profile');
      }
    } catch (err) {
      console.error('MFA verification failed:', err);
      setError('Invalid verification code. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };
  
  const handleDownloadCodes = () => {
    const element = document.createElement('a');
    const file = new Blob([recoveryCodes.join('\n')], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = 'mfa-recovery-codes.txt';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };
  
  const handleCopyCodes = () => {
    navigator.clipboard.writeText(recoveryCodes.join('\n'));
    toast.success('Recovery codes copied to clipboard');
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md mx-auto bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-8">
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-2xl font-bold text-gray-900">Set up two-factor authentication</h2>
                <p className="mt-1 text-sm text-gray-500">
                  Scan the QR code below with your authenticator app.
                </p>
              </div>
              
              <div className="flex justify-center">
                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  {qrCodeUrl ? (
                    <img 
                      src={qrCodeUrl} 
                      alt="MFA QR Code" 
                      className="w-48 h-48"
                    />
                  ) : (
                    <div className="w-48 h-48 flex items-center justify-center bg-gray-100">
                      <p className="text-sm text-gray-500">Loading QR code...</p>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="mt-4">
                <p className="text-sm text-gray-600 text-center">
                  Or enter this code manually:
                </p>
                <div className="mt-2 flex justify-center">
                  <div className="bg-gray-100 px-4 py-2 rounded-md font-mono text-lg">
                    {secret.match(/.{1,4}/g).join(' ')}
                  </div>
                </div>
              </div>
              
              <div className="mt-6">
                <p className="text-sm text-gray-600">
                  We recommend using one of these authenticator apps:
                </p>
                <div className="mt-2 grid grid-cols-3 gap-4">
                  <a 
                    href="https://support.google.com/accounts/answer/1066447" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="flex flex-col items-center p-2 rounded-md hover:bg-gray-50"
                  >
                    <img 
                      src="https://www.gstatic.com/mobilesdk/160503_mobilesdk/logo/2x/firebase_96dp.png" 
                      alt="Google Authenticator" 
                      className="h-12 w-12"
                    />
                    <span className="mt-2 text-xs text-center">Google Authenticator</span>
                  </a>
                  <a 
                    href="https://authy.com/" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="flex flex-col items-center p-2 rounded-md hover:bg-gray-50"
                  >
                    <img 
                      src="https://authy.com/favicon.ico" 
                      alt="Authy" 
                      className="h-12 w-12"
                    />
                    <span className="mt-2 text-xs text-center">Authy</span>
                  </a>
                  <a 
                    href="https://microsoft.com/authenticator" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="flex flex-col items-center p-2 rounded-md hover:bg-gray-50"
                  >
                    <img 
                      src="https://www.microsoft.com/favicon.ico" 
                      alt="Microsoft Authenticator" 
                      className="h-12 w-12"
                    />
                    <span className="mt-2 text-xs text-center">Microsoft Authenticator</span>
                  </a>
                </div>
              </div>
              
              <div className="mt-6">
                <button
                  onClick={() => setStep(2)}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  I've set up my authenticator app
                </button>
              </div>
            </div>
          )}
          
          {step === 2 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-2xl font-bold text-gray-900">Verify your authenticator app</h2>
                <p className="mt-1 text-sm text-gray-500">
                  Enter the 6-digit code from your authenticator app.
                </p>
              </div>
              
              <form onSubmit={handleVerifyCode} className="space-y-4">
                <div>
                  <label htmlFor="verificationCode" className="block text-sm font-medium text-gray-700">
                    Verification code
                  </label>
                  <div className="mt-1">
                    <input
                      id="verificationCode"
                      name="verificationCode"
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      autoComplete="one-time-code"
                      maxLength={6}
                      value={verificationCode}
                      onChange={(e) => {
                        setVerificationCode(e.target.value.replace(/[^0-9]/g, '').slice(0, 6));
                        setError('');
                      }}
                      className={`appearance-none block w-full px-3 py-2 border ${
                        error ? 'border-red-300' : 'border-gray-300'
                      } rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm`}
                      placeholder="123456"
                    />
                  </div>
                  {error && (
                    <p className="mt-2 text-sm text-red-600">{error}</p>
                  )}
                </div>
                
                <div className="flex justify-between">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="inline-flex justify-center py-2 px-4 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                  >
                    Back
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? 'Verifying...' : 'Verify and enable'}
                  </button>
                </div>
              </form>
            </div>
          )}
          
          {step === 3 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-2xl font-bold text-gray-900">Save your recovery codes</h2>
                <p className="mt-1 text-sm text-gray-500">
                  Store these recovery codes in a safe place. You can use them to access your account if you lose access to your authenticator app.
                </p>
                
                <div className="mt-4 bg-gray-50 p-4 rounded-md">
                  <div className="grid grid-cols-2 gap-2 font-mono text-sm">
                    {recoveryCodes.map((code, index) => (
                      <div key={index} className="p-2 bg-white rounded">
                        {code}
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="mt-4 flex flex-col sm:flex-row gap-3">
                  <button
                    type="button"
                    onClick={handleDownloadCodes}
                    className="inline-flex justify-center items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                  >
                    <svg className="-ml-1 mr-2 h-5 w-5 text-gray-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                    Download
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyCodes}
                    className="inline-flex justify-center items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                  >
                    <svg className="-ml-1 mr-2 h-5 w-5 text-gray-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M8 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z" />
                      <path d="M6 3a2 2 0 00-2 2v11a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2 3 3 0 01-3 3H9a3 3 0 01-3-3z" />
                    </svg>
                    Copy to clipboard
                  </button>
                </div>
                
                <div className="mt-6">
                  <div className="rounded-md bg-blue-50 p-4">
                    <div className="flex">
                      <div className="flex-shrink-0">
                        <svg className="h-5 w-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h2a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                        </svg>
                      </div>
                      <div className="ml-3">
                        <h3 className="text-sm font-medium text-blue-800">Important</h3>
                        <div className="mt-2 text-sm text-blue-700">
                          <p>These recovery codes are only shown once. If you lose them, you may lose access to your account.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="mt-6">
                  <button
                    onClick={() => {
                      toast.success('Two-factor authentication has been enabled');
                      navigate('/profile');
                    }}
                    className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                  >
                    I've saved my recovery codes
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MFASetup;
