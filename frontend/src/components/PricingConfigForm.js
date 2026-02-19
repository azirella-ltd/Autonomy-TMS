import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, Input, Label } from './common';

const PricingConfigForm = ({ pricingConfig, onChange }) => {
  const handlePriceChange = (role, field, value) => {
    const newPricingConfig = {
      ...pricingConfig,
      [role]: {
        ...pricingConfig[role],
        [field]: parseFloat(value) || 0
      }
    };
    onChange(newPricingConfig);
  };

  const renderRolePricing = (role, label) => (
    <Card className="mb-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{label} Pricing</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Label htmlFor={`${role}-selling-price`}>Selling Price</Label>
            <Input
              id={`${role}-selling-price`}
              type="number"
              min={0.01}
              max={10000}
              step={0.01}
              value={pricingConfig[role]?.selling_price || ''}
              onChange={(e) => handlePriceChange(role, 'selling_price', e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor={`${role}-standard-cost`}>Standard Cost</Label>
            <Input
              id={`${role}-standard-cost`}
              type="number"
              min={0.01}
              max={10000}
              step={0.01}
              value={pricingConfig[role]?.standard_cost || ''}
              onChange={(e) => handlePriceChange(role, 'standard_cost', e.target.value)}
            />
          </div>
        </div>

        {pricingConfig[role]?.selling_price > 0 && pricingConfig[role]?.standard_cost > 0 && (
          <div className="mt-2">
            <p className="text-sm text-muted-foreground">
              Margin: ${(pricingConfig[role].selling_price - pricingConfig[role].standard_cost).toFixed(2)}
              ({(pricingConfig[role].selling_price > 0 ?
                  ((pricingConfig[role].selling_price - pricingConfig[role].standard_cost) / pricingConfig[role].selling_price * 100).toFixed(1) :
                  '0.0')}%)
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>Pricing Configuration</CardTitle>
        <p className="text-sm text-muted-foreground">
          Configure pricing for each role in the supply chain
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-4">
          {renderRolePricing('retailer', 'Retailer')}
          {renderRolePricing('wholesaler', 'Wholesaler')}
          {renderRolePricing('distributor', 'Distributor')}
          {renderRolePricing('manufacturer', 'Manufacturer')}
        </div>
      </CardContent>
    </Card>
  );
};

export default PricingConfigForm;
