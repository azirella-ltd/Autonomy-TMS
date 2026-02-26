import { useState, useEffect } from "react";
import {
  HandshakeIcon,
  PlusIcon,
  CheckIcon,
  XMarkIcon,
  ChatBubbleLeftIcon,
  ArrowPathIcon,
  LightBulbIcon,
} from "@heroicons/react/24/outline";
import { toast } from "react-toastify";
import simulationApi from "../../services/api";

/**
 * NegotiationPanel Component
 * Phase 7 Sprint 4 - Feature 4: Agent Negotiation
 *
 * Enables inter-scenarioUser negotiations with:
 * - Proposal creation (order adjustment, lead time, inventory share, price adjustment)
 * - Accept/reject/counter workflow
 * - AI-mediated suggestion generation
 * - Impact simulation
 * - Negotiation messaging
 */
const NegotiationPanel = ({ scenarioId, scenarioUserRole, currentScenarioUserId }) => {
  const [negotiations, setNegotiations] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedNegotiation, setSelectedNegotiation] = useState(null);

  // Create form state
  const [targetScenarioUser, setTargetScenarioUser] = useState("");
  const [negotiationType, setNegotiationType] = useState("order_adjustment");
  const [proposal, setProposal] = useState({});
  const [message, setMessage] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    fetchNegotiations();
  }, [scenarioId]);

  const fetchNegotiations = async () => {
    try {
      setIsLoading(true);
      const response = await simulationApi.getScenarioUserNegotiations(scenarioId);
      setNegotiations(response.negotiations || []);
    } catch (error) {
      console.error("Failed to fetch negotiations:", error);
      toast.error("Failed to load negotiations");
    } finally {
      setIsLoading(false);
    }
  };

  const createNegotiation = async () => {
    if (!targetScenarioUser) {
      toast.error("Please select a target scenarioUser");
      return;
    }

    try {
      setIsCreating(true);

      const proposalData = {
        target_scenario_user_id: parseInt(targetScenarioUser),
        negotiation_type: negotiationType,
        proposal: proposal,
        message: message || undefined,
      };

      await simulationApi.createNegotiation(scenarioId, proposalData);
      toast.success("Negotiation proposal created!");

      // Reset form
      setShowCreateForm(false);
      setTargetScenarioUser("");
      setProposal({});
      setMessage("");

      // Refresh list
      fetchNegotiations();
    } catch (error) {
      console.error("Failed to create negotiation:", error);
      toast.error(error.response?.data?.detail || "Failed to create proposal");
    } finally {
      setIsCreating(false);
    }
  };

  const respondToNegotiation = async (negotiationId, action, counterProposal = null) => {
    try {
      const responseData = {
        action,
        counter_proposal: counterProposal,
        message: null,
      };

      await simulationApi.respondToNegotiation(negotiationId, responseData);
      toast.success(`Negotiation ${action}ed!`);

      // Refresh list
      fetchNegotiations();
      setSelectedNegotiation(null);
    } catch (error) {
      console.error("Failed to respond to negotiation:", error);
      toast.error(error.response?.data?.detail || "Failed to respond");
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case "pending":
        return "bg-yellow-100 text-yellow-800";
      case "accepted":
        return "bg-green-100 text-green-800";
      case "rejected":
        return "bg-red-100 text-red-800";
      case "countered":
        return "bg-blue-100 text-blue-800";
      case "expired":
        return "bg-gray-100 text-gray-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  const getTypeLabel = (type) => {
    const labels = {
      order_adjustment: "Order Adjustment",
      lead_time: "Lead Time",
      inventory_share: "Inventory Share",
      price_adjustment: "Price Adjustment",
    };
    return labels[type] || type;
  };

  const renderProposalDetails = (proposalStr) => {
    try {
      const prop = typeof proposalStr === "string" ? JSON.parse(proposalStr) : proposalStr;
      return (
        <div className="text-xs space-y-1">
          {Object.entries(prop).map(([key, value]) => (
            <div key={key} className="flex justify-between">
              <span className="text-gray-600 capitalize">{key.replace(/_/g, " ")}:</span>
              <span className="font-medium">{String(value)}</span>
            </div>
          ))}
        </div>
      );
    } catch (e) {
      return <div className="text-xs text-gray-500">Invalid proposal format</div>;
    }
  };

  const renderCreateForm = () => {
    return (
      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Create Proposal</h3>
          <button
            onClick={() => setShowCreateForm(false)}
            className="text-gray-500 hover:text-gray-700"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Target User */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Target User
          </label>
          <select
            value={targetScenarioUser}
            onChange={(e) => setTargetScenarioUser(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Select user...</option>
            <option value="1">Retailer</option>
            <option value="2">Wholesaler</option>
            <option value="3">Distributor</option>
            <option value="4">Factory</option>
          </select>
        </div>

        {/* Negotiation Type */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Negotiation Type
          </label>
          <select
            value={negotiationType}
            onChange={(e) => {
              setNegotiationType(e.target.value);
              setProposal({}); // Reset proposal on type change
            }}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
          >
            <option value="order_adjustment">Order Adjustment</option>
            <option value="inventory_share">Inventory Share</option>
            <option value="lead_time">Lead Time Change</option>
            <option value="price_adjustment">Price Adjustment</option>
          </select>
        </div>

        {/* Dynamic Proposal Fields */}
        {negotiationType === "order_adjustment" && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Quantity Change
            </label>
            <input
              type="number"
              value={proposal.quantity_change || ""}
              onChange={(e) =>
                setProposal({ ...proposal, quantity_change: parseInt(e.target.value) })
              }
              placeholder="e.g., +20 or -10"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        )}

        {negotiationType === "inventory_share" && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Units to Share
              </label>
              <input
                type="number"
                value={proposal.units || ""}
                onChange={(e) =>
                  setProposal({ ...proposal, units: parseInt(e.target.value) })
                }
                placeholder="e.g., 30"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Direction
              </label>
              <select
                value={proposal.direction || "give"}
                onChange={(e) => setProposal({ ...proposal, direction: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              >
                <option value="give">Give to them</option>
                <option value="receive">Receive from them</option>
              </select>
            </div>
          </>
        )}

        {negotiationType === "lead_time" && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Lead Time Change (rounds)
              </label>
              <input
                type="number"
                value={proposal.lead_time_change || ""}
                onChange={(e) =>
                  setProposal({ ...proposal, lead_time_change: parseInt(e.target.value) })
                }
                placeholder="e.g., -1 (faster) or +1 (slower)"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Compensation ($)
              </label>
              <input
                type="number"
                value={proposal.compensation || ""}
                onChange={(e) =>
                  setProposal({ ...proposal, compensation: parseFloat(e.target.value) })
                }
                placeholder="e.g., 10"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </>
        )}

        {negotiationType === "price_adjustment" && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Price Change ($/unit)
              </label>
              <input
                type="number"
                step="0.1"
                value={proposal.price_change || ""}
                onChange={(e) =>
                  setProposal({ ...proposal, price_change: parseFloat(e.target.value) })
                }
                placeholder="e.g., -5 (discount) or +2 (increase)"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Volume Commitment
              </label>
              <input
                type="number"
                value={proposal.volume_commitment || ""}
                onChange={(e) =>
                  setProposal({ ...proposal, volume_commitment: parseInt(e.target.value) })
                }
                placeholder="e.g., 100"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </>
        )}

        {/* Message */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Message (Optional)
          </label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Add a message to your proposal..."
            rows={2}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 resize-none"
          />
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={createNegotiation}
            disabled={isCreating}
            className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-400"
          >
            {isCreating ? "Creating..." : "Create Proposal"}
          </button>
          <button
            onClick={() => setShowCreateForm(false)}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  };

  const renderNegotiationCard = (neg) => {
    const isPending = neg.status === "pending";
    const isTarget = neg.is_target;
    const canRespond = isPending && isTarget;

    return (
      <div
        key={neg.id}
        className="bg-white rounded-lg shadow p-4 space-y-3 border-l-4"
        style={{
          borderLeftColor: isPending ? "#f59e0b" : "#9ca3af",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HandshakeIcon className="h-5 w-5 text-gray-600" />
            <span className="font-medium text-sm">
              {neg.initiator_role} → {neg.target_role}
            </span>
          </div>
          <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(neg.status)}`}>
            {neg.status}
          </span>
        </div>

        {/* Type */}
        <div className="text-sm">
          <span className="text-gray-600">Type:</span>{" "}
          <span className="font-medium">{getTypeLabel(neg.negotiation_type)}</span>
        </div>

        {/* Proposal */}
        <div className="bg-gray-50 rounded p-3">
          <div className="text-xs text-gray-600 mb-2">Proposal:</div>
          {renderProposalDetails(neg.proposal)}
        </div>

        {/* Counter Proposal (if exists) */}
        {neg.counter_proposal && (
          <div className="bg-blue-50 rounded p-3 border border-blue-200">
            <div className="text-xs text-blue-600 mb-2">Counter Proposal:</div>
            {renderProposalDetails(neg.counter_proposal)}
          </div>
        )}

        {/* Actions */}
        {canRespond && (
          <div className="flex gap-2 pt-2 border-t">
            <button
              onClick={() => respondToNegotiation(neg.id, "accept")}
              className="flex-1 px-3 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700 flex items-center justify-center gap-1"
            >
              <CheckIcon className="h-4 w-4" />
              Accept
            </button>
            <button
              onClick={() => respondToNegotiation(neg.id, "reject")}
              className="flex-1 px-3 py-2 bg-red-600 text-white rounded text-sm hover:bg-red-700 flex items-center justify-center gap-1"
            >
              <XMarkIcon className="h-4 w-4" />
              Reject
            </button>
          </div>
        )}

        {/* Timestamps */}
        <div className="text-xs text-gray-500 pt-2 border-t">
          Created: {new Date(neg.created_at).toLocaleString()}
          {neg.expires_at && (
            <div>Expires: {new Date(neg.expires_at).toLocaleString()}</div>
          )}
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <ArrowPathIcon className="h-12 w-12 text-indigo-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-600">Loading negotiations...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <HandshakeIcon className="h-6 w-6 text-indigo-600" />
          <h2 className="text-2xl font-bold text-gray-900">Negotiations</h2>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchNegotiations}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 text-sm"
          >
            Refresh
          </button>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 text-sm flex items-center gap-2"
          >
            <PlusIcon className="h-5 w-5" />
            New Proposal
          </button>
        </div>
      </div>

      {/* Create Form */}
      {showCreateForm && renderCreateForm()}

      {/* Negotiations List */}
      {negotiations.length > 0 ? (
        <div className="grid grid-cols-1 gap-4">
          {negotiations.map((neg) => renderNegotiationCard(neg))}
        </div>
      ) : (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <HandshakeIcon className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-600 mb-2">No negotiations yet</p>
          <p className="text-sm text-gray-400 mb-4">
            Start negotiating with other users to optimize the supply chain
          </p>
          <button
            onClick={() => setShowCreateForm(true)}
            className="px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            Create First Proposal
          </button>
        </div>
      )}
    </div>
  );
};

export default NegotiationPanel;
