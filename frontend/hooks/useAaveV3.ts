// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback } from 'react'
import { ethers } from 'ethers'
import { toast } from 'sonner'
import { useWallet } from './useWallet'
import { AAVE_V3_ADDRESSES, TOKEN_ADDRESSES, getChainKey, SupportedToken } from '@/lib/web3/config'
import { AAVE_POOL_ABI } from '@/lib/web3/abi/aavePool'
import { ERC20_ABI } from '@/lib/web3/abi/erc20'
import type { AaveUserAccountData, InterestRateMode } from '@/types/web3'

export function useAaveV3() {
  const { signer, chainId, address, isConnected } = useWallet()

  const getPoolContract = useCallback(() => {
    if (!signer || !chainId) throw new Error('ウォレット未接続')
    const chainKey = getChainKey(chainId)
    if (!chainKey) throw new Error('非対応ネットワーク')
    const poolAddress = AAVE_V3_ADDRESSES[chainKey].Pool
    return new ethers.Contract(poolAddress, AAVE_POOL_ABI, signer)
  }, [signer, chainId])

  const getTokenAddress = useCallback((token: SupportedToken): string => {
    const chainKey = getChainKey(chainId ?? 0)
    if (!chainKey) throw new Error('非対応ネットワーク')
    return TOKEN_ADDRESSES[chainKey][token]
  }, [chainId])

  const getUserAccountData = useCallback(async (userAddress?: string): Promise<AaveUserAccountData> => {
    const pool = getPoolContract()
    const target = userAddress ?? address
    if (!target) throw new Error('アドレス未指定')
    const data = await pool.getUserAccountData(target)
    return {
      totalCollateralBase: data.totalCollateralBase,
      totalDebtBase: data.totalDebtBase,
      availableBorrowsBase: data.availableBorrowsBase,
      currentLiquidationThreshold: data.currentLiquidationThreshold,
      ltv: data.ltv,
      healthFactor: data.healthFactor,
    }
  }, [getPoolContract, address])

  const approve = useCallback(async (token: SupportedToken, amount: bigint): Promise<ethers.TransactionResponse> => {
    if (!signer || !chainId) throw new Error('ウォレット未接続')
    const tokenAddress = getTokenAddress(token)
    const chainKey = getChainKey(chainId)
    if (!chainKey) throw new Error('非対応ネットワーク')
    const poolAddress = AAVE_V3_ADDRESSES[chainKey].Pool
    const erc20 = new ethers.Contract(tokenAddress, ERC20_ABI, signer)
    try {
      const tx = await erc20.approve(poolAddress, amount)
      toast('承認トランザクションを送信しました')
      return tx
    } catch (err) {
      const msg = err instanceof Error ? err.message : '承認に失敗しました'
      toast.error(msg)
      throw err
    }
  }, [signer, chainId, getTokenAddress])

  const supply = useCallback(async (token: SupportedToken, amount: bigint): Promise<ethers.TransactionResponse> => {
    const pool = getPoolContract()
    const tokenAddress = getTokenAddress(token)
    if (!address) throw new Error('アドレス未取得')
    try {
      const tx = await pool.supply(tokenAddress, amount, address, 0)
      toast('供給トランザクションを送信しました')
      return tx
    } catch (err) {
      const msg = err instanceof Error ? err.message : '供給に失敗しました'
      toast.error(msg)
      throw err
    }
  }, [getPoolContract, getTokenAddress, address])

  const withdraw = useCallback(async (token: SupportedToken, amount: bigint): Promise<ethers.TransactionResponse> => {
    const pool = getPoolContract()
    const tokenAddress = getTokenAddress(token)
    if (!address) throw new Error('アドレス未取得')
    try {
      const tx = await pool.withdraw(tokenAddress, amount, address)
      toast('引き出しトランザクションを送信しました')
      return tx
    } catch (err) {
      const msg = err instanceof Error ? err.message : '引き出しに失敗しました'
      toast.error(msg)
      throw err
    }
  }, [getPoolContract, getTokenAddress, address])

  const borrow = useCallback(async (
    token: SupportedToken,
    amount: bigint,
    interestRateMode: InterestRateMode = 2,
  ): Promise<ethers.TransactionResponse> => {
    const pool = getPoolContract()
    const tokenAddress = getTokenAddress(token)
    if (!address) throw new Error('アドレス未取得')
    try {
      const tx = await pool.borrow(tokenAddress, amount, interestRateMode, 0, address)
      toast('借入トランザクションを送信しました')
      return tx
    } catch (err) {
      const msg = err instanceof Error ? err.message : '借入に失敗しました'
      toast.error(msg)
      throw err
    }
  }, [getPoolContract, getTokenAddress, address])

  const repay = useCallback(async (
    token: SupportedToken,
    amount: bigint,
    interestRateMode: InterestRateMode = 2,
  ): Promise<ethers.TransactionResponse> => {
    const pool = getPoolContract()
    const tokenAddress = getTokenAddress(token)
    if (!address) throw new Error('アドレス未取得')
    try {
      const tx = await pool.repay(tokenAddress, amount, interestRateMode, address)
      toast('返済トランザクションを送信しました')
      return tx
    } catch (err) {
      const msg = err instanceof Error ? err.message : '返済に失敗しました'
      toast.error(msg)
      throw err
    }
  }, [getPoolContract, getTokenAddress, address])

  return {
    isReady: isConnected && !!signer,
    getUserAccountData,
    approve,
    supply,
    withdraw,
    borrow,
    repay,
  }
}
