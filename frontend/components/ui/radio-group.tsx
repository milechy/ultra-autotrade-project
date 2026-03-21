// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'

interface RadioGroupContextValue {
  value: string
  onValueChange: (value: string) => void
  name: string
}

const RadioGroupContext = React.createContext<RadioGroupContextValue>({
  value: '',
  onValueChange: () => {},
  name: '',
})

interface RadioGroupProps {
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  className?: string
  children?: React.ReactNode
  name?: string
}

const RadioGroup = React.forwardRef<HTMLDivElement, RadioGroupProps>(
  ({ value, defaultValue = '', onValueChange, className, children, name = 'radio-group', ...props }, ref) => {
    const [internalValue, setInternalValue] = React.useState(defaultValue)
    const controlled = value !== undefined
    const currentValue = controlled ? value : internalValue

    const handleChange = React.useCallback(
      (v: string) => {
        if (!controlled) setInternalValue(v)
        onValueChange?.(v)
      },
      [controlled, onValueChange]
    )

    return (
      <RadioGroupContext.Provider value={{ value: currentValue ?? '', onValueChange: handleChange, name }}>
        <div ref={ref} role="radiogroup" className={cn('grid gap-2', className)} {...props}>
          {children}
        </div>
      </RadioGroupContext.Provider>
    )
  }
)
RadioGroup.displayName = 'RadioGroup'

interface RadioGroupItemProps extends React.InputHTMLAttributes<HTMLInputElement> {
  value: string
}

const RadioGroupItem = React.forwardRef<HTMLInputElement, RadioGroupItemProps>(
  ({ value, className, id, ...props }, ref) => {
    const ctx = React.useContext(RadioGroupContext)
    const checked = ctx.value === value

    return (
      <input
        ref={ref}
        type="radio"
        id={id}
        name={ctx.name}
        value={value}
        checked={checked}
        onChange={() => ctx.onValueChange(value)}
        className={cn(
          'h-4 w-4 rounded-full border border-zinc-600 text-primary focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 accent-primary cursor-pointer',
          className
        )}
        {...props}
      />
    )
  }
)
RadioGroupItem.displayName = 'RadioGroupItem'

export { RadioGroup, RadioGroupItem }
