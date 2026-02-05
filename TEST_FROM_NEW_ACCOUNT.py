# Test file from ultraautotrade-test account
   # This PR is created to test Slack approval workflow
   
   def test_approval():
       print("Testing Slack approval workflow")
       return True
   
   if __name__ == "__main__":
       test_approval()
```

7. **"Commit new file" をクリック**
   - Commit directly to the `test/approval-from-test-account` branch
   - Commit message: `test: Add file from test account`

---

## 📤 ステップ3: Pull Request を作成

**ファイルをコミット後、自動的に表示されるバナーで:**

**"Compare & pull request" ボタンをクリック**

または、以下のURLにアクセス:
```
https://github.com/milechy/ultra-autotrade-project/compare/main...ultraautotrade-test:ultra-autotrade-project:test/approval-from-test-account
```

**PR設定:**
```
Title: test: Approval workflow test from new account
Base repository: milechy/ultra-autotrade-project
Base: main
Compare: ultraautotrade-test:test/approval-from-test-account
