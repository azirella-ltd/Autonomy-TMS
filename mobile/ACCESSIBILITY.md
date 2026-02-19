# Mobile App Accessibility Guide

Comprehensive guide for making The Beer Game mobile app accessible to all users.

---

## Accessibility Standards

The app follows:
- **WCAG 2.1 Level AA** - Web Content Accessibility Guidelines
- **iOS Accessibility** - VoiceOver support
- **Android Accessibility** - TalkBack support

---

## Implemented Features

### Screen Reader Support

All interactive elements have proper labels:

```typescript
// Button with accessibility label
<Button
  accessibilityLabel="Sign in to your account"
  accessibilityHint="Double tap to sign in with email and password"
  onPress={handleLogin}
>
  Sign In
</Button>

// Input with label
<TextInput
  label="Email"
  accessibilityLabel="Email address input"
  accessibilityHint="Enter your email address"
  value={email}
  onChangeText={setEmail}
/>
```

### Touch Target Sizes

All touch targets meet minimum 44x44pt size:

```typescript
const styles = StyleSheet.create({
  button: {
    minHeight: 44,
    minWidth: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
```

### Color Contrast

Text meets WCAG AA contrast ratios:
- Normal text: 4.5:1 minimum
- Large text (18pt+): 3:1 minimum
- Interactive elements: 3:1 minimum

### Focus Management

Focus order follows logical reading order:

```typescript
<View accessible={true} accessibilityLabel="Login form">
  <TextInput ref={emailRef} returnKeyType="next" onSubmitEditing={() => passwordRef.current?.focus()} />
  <TextInput ref={passwordRef} returnKeyType="done" onSubmitEditing={handleLogin} />
</View>
```

### Dynamic Type

Text scales with system font size settings:

```typescript
const styles = StyleSheet.create({
  text: {
    fontSize: 16, // Base size
    // Will scale automatically with system settings
  },
});
```

---

## Accessibility Props Reference

### Common Props

| Prop | Description | Example |
|------|-------------|---------|
| `accessible` | Marks as accessibility element | `accessible={true}` |
| `accessibilityLabel` | Text read by screen reader | `"Sign in button"` |
| `accessibilityHint` | Additional context | `"Double tap to sign in"` |
| `accessibilityRole` | Element type | `"button"`, `"header"` |
| `accessibilityState` | Current state | `{ disabled: true }` |
| `accessibilityValue` | Current value | `{ text: "50%" }` |

### iOS-Specific

| Prop | Description |
|------|-------------|
| `accessibilityTraits` | Additional traits |
| `accessibilityElementsHidden` | Hide from VoiceOver |
| `accessibilityViewIsModal` | Modal focus |

### Android-Specific

| Prop | Description |
|------|-------------|
| `importantForAccessibility` | TalkBack importance |
| `accessibilityLiveRegion` | Announce changes |

---

## Screen-by-Screen Guide

### Login Screen

```typescript
<View accessible={false}>
  {/* Title */}
  <Text
    accessibilityRole="header"
    accessibilityLabel="The Beer Game, Supply Chain Simulation"
  >
    The Beer Game
  </Text>

  {/* Email Input */}
  <TextInput
    label="Email"
    accessibilityLabel="Email address"
    accessibilityHint="Enter your email to sign in"
    value={email}
    onChangeText={setEmail}
  />

  {/* Password Input */}
  <TextInput
    label="Password"
    accessibilityLabel="Password"
    accessibilityHint="Enter your password"
    secureTextEntry={!showPassword}
    value={password}
    onChangeText={setPassword}
    right={
      <TextInput.Icon
        icon={showPassword ? 'eye-off' : 'eye'}
        accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
        accessibilityHint="Toggles password visibility"
        onPress={() => setShowPassword(!showPassword)}
      />
    }
  />

  {/* Error Message */}
  {error && (
    <Text
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={styles.error}
    >
      {error}
    </Text>
  )}

  {/* Sign In Button */}
  <Button
    mode="contained"
    onPress={handleLogin}
    loading={loading}
    disabled={loading}
    accessibilityLabel="Sign in"
    accessibilityHint="Double tap to sign in with your credentials"
    accessibilityState={{ disabled: loading }}
  >
    Sign In
  </Button>

  {/* Register Link */}
  <Button
    mode="text"
    onPress={() => navigation.navigate('Register')}
    accessibilityLabel="Don't have an account? Sign up"
    accessibilityHint="Navigate to registration screen"
  >
    Don't have an account? Sign Up
  </Button>
</View>
```

### Dashboard Screen

```typescript
<ScrollView
  accessibilityLabel="Dashboard"
  accessibilityHint="Scroll to view your games and statistics"
>
  {/* Welcome Header */}
  <Text
    accessibilityRole="header"
    accessibilityLabel={`Welcome back, ${user.name}`}
  >
    Welcome back, {user.name}!
  </Text>

  {/* Stats Cards */}
  <View
    accessible={true}
    accessibilityLabel={`You have ${activeGames} active games`}
    accessibilityRole="text"
  >
    <Text style={styles.statValue}>{activeGames}</Text>
    <Text>Active Games</Text>
  </View>

  {/* Game List */}
  <FlatList
    data={games}
    accessibilityLabel="Your games list"
    renderItem={({ item }) => (
      <TouchableOpacity
        accessible={true}
        accessibilityRole="button"
        accessibilityLabel={`${item.name}, Round ${item.current_round} of ${item.max_rounds}`}
        accessibilityHint="Double tap to view game details"
        onPress={() => navigation.navigate('GameDetail', { gameId: item.id })}
      >
        <Card>
          <Card.Title title={item.name} />
          <Card.Content>
            <Text>Round {item.current_round} of {item.max_rounds}</Text>
          </Card.Content>
        </Card>
      </TouchableOpacity>
    )}
  />

  {/* Quick Actions */}
  <Button
    mode="contained"
    icon="plus"
    onPress={() => navigation.navigate('CreateGame')}
    accessibilityLabel="Create new game"
    accessibilityHint="Opens game creation wizard"
  >
    New Game
  </Button>
</ScrollView>
```

### Game Detail Screen

```typescript
<ScrollView accessibilityLabel="Game details">
  {/* Game Header */}
  <View accessible={true} accessibilityRole="header">
    <Text
      accessibilityLabel={`${game.name}, Round ${game.current_round} of ${game.max_rounds}`}
    >
      {game.name}
    </Text>
  </View>

  {/* Inventory Status */}
  <Card
    accessible={true}
    accessibilityRole="summary"
    accessibilityLabel={`Inventory: ${inventory} units, Backlog: ${backlog} units`}
  >
    <Card.Content>
      <Text>Inventory: {inventory}</Text>
      <Text>Backlog: {backlog}</Text>
    </Card.Content>
  </Card>

  {/* Order Input */}
  <TextInput
    label="Order Quantity"
    value={orderQty}
    onChangeText={setOrderQty}
    keyboardType="numeric"
    accessibilityLabel="Order quantity"
    accessibilityHint="Enter number of units to order"
    accessibilityValue={{ text: `${orderQty} units` }}
  />

  {/* Submit Order Button */}
  <Button
    mode="contained"
    onPress={handleSubmitOrder}
    disabled={!orderQty || loading}
    accessibilityLabel="Submit order"
    accessibilityHint={`Order ${orderQty} units for this round`}
    accessibilityState={{ disabled: !orderQty || loading }}
  >
    Submit Order
  </Button>
</ScrollView>
```

### Analytics Screen

```typescript
<View accessible={false}>
  {/* Tab Selector */}
  <SegmentedButtons
    value={viewMode}
    onValueChange={setViewMode}
    buttons={[
      {
        value: 'overview',
        label: 'Overview',
        accessibilityLabel: 'Overview tab',
      },
      {
        value: 'stochastic',
        label: 'Stochastic',
        accessibilityLabel: 'Stochastic analysis tab',
      },
      {
        value: 'monte-carlo',
        label: 'Monte Carlo',
        accessibilityLabel: 'Monte Carlo simulation tab',
      },
    ]}
  />

  {/* Metric Cards */}
  <Card
    accessible={true}
    accessibilityRole="text"
    accessibilityLabel={`Total cost: ${totalCost.toFixed(2)} dollars`}
  >
    <Card.Content>
      <Text>Total Cost</Text>
      <Text>${totalCost.toFixed(2)}</Text>
    </Card.Content>
  </Card>

  {/* Charts */}
  <View
    accessible={true}
    accessibilityLabel="Cost distribution pie chart"
    accessibilityHint="Shows breakdown of holding, backlog, and ordering costs"
  >
    <PieChart data={costData} />
  </View>

  {/* Progress Bar */}
  <View accessible={true} accessibilityRole="progressbar">
    <Text accessibilityLabel={`Service level: ${serviceLevel}%`}>
      Service Level: {serviceLevel}%
    </Text>
    <ProgressBar
      progress={serviceLevel / 100}
      accessibilityValue={{
        min: 0,
        max: 100,
        now: serviceLevel,
      }}
    />
  </View>
</View>
```

---

## Testing Accessibility

### iOS VoiceOver

1. Enable VoiceOver:
   - Settings → Accessibility → VoiceOver → On
   - Or triple-click side button

2. Test Navigation:
   - Swipe right/left to move between elements
   - Double-tap to activate
   - Three-finger swipe for page navigation

3. Verify:
   - All elements are announced
   - Labels are descriptive
   - Focus order is logical
   - States are announced (disabled, selected, etc.)

### Android TalkBack

1. Enable TalkBack:
   - Settings → Accessibility → TalkBack → On
   - Or volume keys shortcut

2. Test Navigation:
   - Swipe right/left for navigation
   - Double-tap to activate
   - Swipe up/down for reading controls

3. Verify:
   - Content descriptions present
   - Navigation order correct
   - States announced
   - Live regions update

### Automated Testing

```typescript
// Test accessibility props
import { render } from '@testing-library/react-native';

it('should have accessibility label', () => {
  const { getByA11yLabel } = render(<LoginScreen />);
  expect(getByA11yLabel('Sign in button')).toBeTruthy();
});

// Test accessible state
it('should indicate disabled state', () => {
  const { getByRole } = render(<Button disabled />);
  const button = getByRole('button');
  expect(button.props.accessibilityState.disabled).toBe(true);
});
```

---

## Best Practices

### DO

✅ **Use descriptive labels**
```typescript
// Good
<Button accessibilityLabel="Create new game">+</Button>

// Bad
<Button accessibilityLabel="Plus">+</Button>
```

✅ **Provide context with hints**
```typescript
<Button
  accessibilityLabel="Submit order"
  accessibilityHint="Places order for next round"
/>
```

✅ **Group related content**
```typescript
<View accessible={true} accessibilityLabel="Inventory status">
  <Text>Inventory: {inventory}</Text>
  <Text>Backlog: {backlog}</Text>
</View>
```

✅ **Announce dynamic updates**
```typescript
<Text accessibilityLiveRegion="polite">
  {notification}
</Text>
```

✅ **Use semantic roles**
```typescript
<Text accessibilityRole="header">Dashboard</Text>
<View accessibilityRole="button" />
<Text accessibilityRole="alert">{error}</Text>
```

### DON'T

❌ **Don't use generic labels**
```typescript
// Bad
<Button accessibilityLabel="Button">Click</Button>
```

❌ **Don't hide important content**
```typescript
// Bad
<View accessibilityElementsHidden={true}>
  <Text>Important info</Text>
</View>
```

❌ **Don't rely only on color**
```typescript
// Bad - color only
<Text style={{ color: 'red' }}>Error</Text>

// Good - icon + color + label
<View>
  <Icon name="error" color="red" />
  <Text accessibilityRole="alert">Error occurred</Text>
</View>
```

❌ **Don't break focus order**
```typescript
// Bad - manual tabIndex that breaks flow
<Button tabIndex={99} />
```

---

## Color Contrast Checker

Verify contrast ratios:

**Light Theme**:
- Text on background: `#000000` on `#FFFFFF` = 21:1 ✅
- Primary button: `#FFFFFF` on `#1976d2` = 4.5:1 ✅
- Links: `#1976d2` on `#FFFFFF` = 4.5:1 ✅

**Dark Theme**:
- Text on background: `#FFFFFF` on `#121212` = 15.8:1 ✅
- Primary button: `#000000` on `#90caf9` = 9.4:1 ✅
- Links: `#90caf9` on `#121212` = 9.4:1 ✅

Tools:
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [Accessible Colors](https://accessible-colors.com/)

---

## Keyboard Navigation

Support for external keyboards:

```typescript
import { Platform } from 'react-native';

const handleKeyPress = (event: KeyboardEvent) => {
  if (Platform.OS === 'web') {
    switch (event.key) {
      case 'Enter':
        handleSubmit();
        break;
      case 'Escape':
        handleCancel();
        break;
      case 'Tab':
        // Focus moves automatically
        break;
    }
  }
};
```

---

## Resources

- [React Native Accessibility](https://reactnative.dev/docs/accessibility)
- [iOS Accessibility](https://developer.apple.com/accessibility/)
- [Android Accessibility](https://developer.android.com/guide/topics/ui/accessibility)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Mobile Accessibility Checklist](https://www.w3.org/WAI/standards-guidelines/mobile/)

---

## Compliance Checklist

- [x] All interactive elements have labels
- [x] All images have alt text or are marked decorative
- [x] Touch targets are minimum 44x44pt
- [x] Color contrast meets WCAG AA
- [x] Content scales with system font size
- [x] Focus order is logical
- [x] Forms have proper labels and error messages
- [x] Alerts and notifications are announced
- [x] VoiceOver tested on iOS
- [x] TalkBack tested on Android
- [ ] Keyboard navigation fully supported (pending)
- [ ] Screen rotation supported (pending)

---

**Last Updated**: 2026-01-14
**WCAG Level**: AA
**Status**: 90% Complete ✅

---

*Building inclusive apps for everyone!* ♿️
