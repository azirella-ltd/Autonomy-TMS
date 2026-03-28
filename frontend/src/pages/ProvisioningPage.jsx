/**
 * ProvisioningPage — Full-page provisioning view for unprovisioned tenants.
 *
 * Shown when a user logs in and their active config has not been provisioned.
 * Embeds the ProvisioningStepper in a full-page layout (not a modal).
 * Once provisioning completes, redirects to the normal landing page.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, ArrowRight, Loader2, ShieldAlert } from 'lucide-react';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { useAuth } from '../contexts/AuthContext';
import ProvisioningStepper from '../components/supply-chain-config/ProvisioningStepper';

export default function ProvisioningPage() {
  const { activeConfig, activeConfigId, refresh, provisioningRequired } = useActiveConfig();
  const { isTenantAdmin } = useAuth();
  const navigate = useNavigate();
  const [stepperOpen, setStepperOpen] = useState(false);

  // If provisioning is no longer required (completed), redirect to dashboard
  useEffect(() => {
    if (!provisioningRequired && activeConfigId) {
      navigate('/dashboard', { replace: true });
    }
  }, [provisioningRequired, activeConfigId, navigate]);

  const handleStepperClose = useCallback(() => {
    setStepperOpen(false);
    // Refresh config context to re-check provisioning status
    refresh();
  }, [refresh]);

  if (!activeConfig) {
    return (
      <div className="flex items-center justify-center min-h-[80vh]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-16">
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 mb-6">
          <Zap className="w-10 h-10 text-white" />
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-3">
          Welcome to Autonomy
        </h1>
        <p className="text-lg text-gray-600 max-w-xl mx-auto">
          Your supply chain config <span className="font-semibold text-gray-900">{activeConfig.name}</span> needs
          to be provisioned before AI agents can start making decisions.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">What does provisioning do?</h2>
        <ul className="space-y-3 text-gray-600">
          <li className="flex items-start gap-3">
            <span className="mt-1 w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
            <span>Simulates historical demand to seed agent training data and belief states</span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-1 w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
            <span>Generates 2-year demand forecasts with P10/P50/P90 confidence intervals</span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-1 w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
            <span>Trains AI agents (strategic, tactical, and execution layers) on your supply chain topology</span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-1 w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">4</span>
            <span>Generates an initial supply plan and calibrates conformal prediction intervals</span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-1 w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">5</span>
            <span>Creates your executive strategy briefing with decision recommendations</span>
          </li>
        </ul>
      </div>

      <div className="text-center">
        {isTenantAdmin ? (
          <>
            <button
              onClick={() => setStepperOpen(true)}
              className="inline-flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold rounded-lg shadow-lg hover:from-blue-700 hover:to-indigo-700 transition-all hover:shadow-xl"
            >
              <Zap className="w-5 h-5" />
              Start Provisioning
              <ArrowRight className="w-5 h-5" />
            </button>
            <p className="mt-3 text-sm text-gray-500">
              Takes 2-5 minutes depending on network complexity
            </p>
          </>
        ) : (
          <div className="inline-flex flex-col items-center gap-3 px-8 py-6 bg-amber-50 border border-amber-200 rounded-xl">
            <ShieldAlert className="w-8 h-8 text-amber-600" />
            <p className="text-gray-700 font-medium">
              Only your tenant administrator can provision this configuration.
            </p>
            <p className="text-sm text-gray-500">
              Please contact your admin to start provisioning.
            </p>
          </div>
        )}
      </div>

      {stepperOpen && (
        <ProvisioningStepper
          isOpen={stepperOpen}
          onClose={handleStepperClose}
          configId={activeConfigId}
          configName={activeConfig.name}
        />
      )}
    </div>
  );
}
