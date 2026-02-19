/**
 * Agent Suggestion Card Component
 * Displays agent order suggestions with confidence and rationale
 * Phase 7 Sprint 2
 */

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, Button, ProgressBar, Chip, useTheme } from 'react-native-paper';
import { AgentSuggestion } from '../../store/slices/chatSlice';
import { chatService } from '../../services/chat';

interface AgentSuggestionCardProps {
  suggestion: AgentSuggestion;
  onAccept: () => void;
  onDecline: () => void;
  disabled?: boolean;
}

export default function AgentSuggestionCard({
  suggestion,
  onAccept,
  onDecline,
  disabled = false,
}: AgentSuggestionCardProps) {
  const theme = useTheme();

  const agentEmoji = chatService.getAgentEmoji(suggestion.agentName);
  const confidenceColor = chatService.getConfidenceColor(suggestion.confidence);
  const isDecided = suggestion.accepted !== undefined;

  return (
    <Card
      style={styles.card}
      accessible={true}
      accessibilityLabel={`Suggestion from ${suggestion.agentName}: Order ${suggestion.orderQuantity} units with ${chatService.formatConfidence(suggestion.confidence)} confidence`}
    >
      {/* Header */}
      <Card.Title
        title={`${agentEmoji} ${suggestion.agentName} Suggestion`}
        titleStyle={styles.title}
        subtitle={`Round ${suggestion.round}`}
        subtitleStyle={styles.subtitle}
        right={() =>
          isDecided && (
            <Chip
              mode="flat"
              style={[
                styles.statusChip,
                {
                  backgroundColor: suggestion.accepted
                    ? theme.colors.primaryContainer
                    : theme.colors.errorContainer,
                },
              ]}
              textStyle={{
                color: suggestion.accepted
                  ? theme.colors.onPrimaryContainer
                  : theme.colors.onErrorContainer,
              }}
            >
              {suggestion.accepted ? '✓ Accepted' : '✗ Declined'}
            </Chip>
          )
        }
      />

      <Card.Content>
        {/* Order Quantity */}
        <View style={styles.orderContainer}>
          <Text style={styles.orderLabel}>Recommended Order:</Text>
          <Text style={[styles.orderValue, { color: theme.colors.primary }]}>
            {suggestion.orderQuantity} units
          </Text>
        </View>

        {/* Confidence */}
        <View style={styles.confidenceContainer}>
          <View style={styles.confidenceHeader}>
            <Text style={styles.confidenceLabel}>Confidence:</Text>
            <Text style={[styles.confidenceValue, { color: confidenceColor }]}>
              {chatService.formatConfidence(suggestion.confidence)}
            </Text>
          </View>
          <ProgressBar
            progress={suggestion.confidence}
            color={confidenceColor}
            style={styles.confidenceBar}
          />
        </View>

        {/* Rationale */}
        <View style={styles.rationaleContainer}>
          <Text style={styles.rationaleLabel}>Rationale:</Text>
          <Text style={styles.rationaleText}>{suggestion.rationale}</Text>
        </View>

        {/* Context */}
        <View style={styles.contextContainer}>
          <Text style={styles.contextLabel}>Context:</Text>
          <View style={styles.contextGrid}>
            <View style={styles.contextItem}>
              <Text style={styles.contextItemLabel}>Current Inventory:</Text>
              <Text style={styles.contextItemValue}>
                {suggestion.context.currentInventory}
              </Text>
            </View>
            <View style={styles.contextItem}>
              <Text style={styles.contextItemLabel}>Current Backlog:</Text>
              <Text style={styles.contextItemValue}>
                {suggestion.context.currentBacklog}
              </Text>
            </View>
            <View style={styles.contextItem}>
              <Text style={styles.contextItemLabel}>Avg Recent Demand:</Text>
              <Text style={styles.contextItemValue}>
                {Math.round(
                  suggestion.context.recentDemand.reduce((a, b) => a + b, 0) /
                    suggestion.context.recentDemand.length
                )}
              </Text>
            </View>
            <View style={styles.contextItem}>
              <Text style={styles.contextItemLabel}>Forecast Demand:</Text>
              <Text style={styles.contextItemValue}>
                {suggestion.context.forecastDemand}
              </Text>
            </View>
          </View>
        </View>
      </Card.Content>

      {/* Actions */}
      {!isDecided && (
        <Card.Actions style={styles.actions}>
          <Button
            mode="outlined"
            onPress={onDecline}
            disabled={disabled}
            accessibilityLabel="Decline suggestion"
            accessibilityHint="Do not use this suggested order quantity"
          >
            Decline
          </Button>
          <Button
            mode="contained"
            onPress={onAccept}
            disabled={disabled}
            accessibilityLabel="Accept suggestion"
            accessibilityHint="Use this suggested order quantity"
          >
            Accept Suggestion
          </Button>
        </Card.Actions>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 12,
    marginVertical: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
  },
  subtitle: {
    fontSize: 12,
  },
  statusChip: {
    marginRight: 12,
  },
  orderContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  orderLabel: {
    fontSize: 14,
    marginRight: 8,
  },
  orderValue: {
    fontSize: 24,
    fontWeight: '700',
  },
  confidenceContainer: {
    marginBottom: 16,
  },
  confidenceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  confidenceLabel: {
    fontSize: 14,
  },
  confidenceValue: {
    fontSize: 16,
    fontWeight: '600',
  },
  confidenceBar: {
    height: 8,
    borderRadius: 4,
  },
  rationaleContainer: {
    marginBottom: 16,
  },
  rationaleLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  rationaleText: {
    fontSize: 14,
    lineHeight: 20,
  },
  contextContainer: {
    marginBottom: 8,
  },
  contextLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  contextGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -4,
  },
  contextItem: {
    width: '50%',
    paddingHorizontal: 4,
    marginBottom: 8,
  },
  contextItemLabel: {
    fontSize: 12,
    opacity: 0.7,
  },
  contextItemValue: {
    fontSize: 16,
    fontWeight: '600',
  },
  actions: {
    justifyContent: 'flex-end',
    paddingHorizontal: 12,
    paddingBottom: 12,
  },
});
