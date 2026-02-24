import React from 'react';
import { render, waitFor } from '@testing-library/react';

// Mock the simulationApi default export used by RoundTimer
jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    getRoundStatus: jest.fn().mockResolvedValue({
      ends_at: new Date(Date.now() + 60_000).toISOString(),
      submitted_players: []
    })
  }
}));

// Mock Chakra UI to avoid pulling full library in tests
jest.mock('@chakra-ui/react', () => ({
  __esModule: true,
  Text: (props) => <div {...props} />,
  Progress: (props) => <div {...props} />,
  VStack: (props) => <div {...props} />,
  HStack: (props) => <div {...props} />,
  Button: (props) => <button {...props} />,
  NumberInput: ({ children, ...rest }) => <div {...rest}>{children}</div>,
  NumberInputField: (props) => <input {...props} />,
  NumberInputStepper: ({ children, ...rest }) => <div {...rest}>{children}</div>,
  NumberIncrementStepper: (props) => <div {...props} />,
  NumberDecrementStepper: (props) => <div {...props} />,
  Badge: (props) => <div {...props} />,
  useToast: () => jest.fn(),
}));

jest.mock('@chakra-ui/icons', () => ({
  __esModule: true,
  CheckCircleIcon: () => null,
  TimeIcon: () => null,
  WarningIcon: () => null,
}));

const RoundTimer = require('../../components/RoundTimer').default;

describe('RoundTimer', () => {
  it('calls getRoundStatus on mount with provided gameId', async () => {
    const api = (await import('../../services/api')).default;

    render(
      <RoundTimer
        gameId={123}
        scenarioUserId={456}
        roundNumber={1}
        onOrderSubmit={jest.fn()}
        isPlayerTurn={false}
      />
    );

    await waitFor(() => expect(api.getRoundStatus).toHaveBeenCalledWith(123));
  });
});
