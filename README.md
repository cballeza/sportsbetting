# SmartBetting: A Sports Betting AI Agent ###
# Carol Balleza

This project is automates the settlement of sports bets. 
It fetches recent game results from The Odds API, determines the outcome of pending bets stored in Firebase Firestore, and automatically updates user wallets using atomic transactions.

# Features

Multi-Sport Support: Almost all sports

Atomic Wallet Updates: Uses Firestore Increment to ensure user bankroll updates are safe and concurrent-proof.

Error Handling: graceful handling of API connection errors or missing data.

# Logic 

Fetch Pending: Queries Firestore for all bets where result == 'PENDING'.

Fetch Scores: Calls The Odds API to get game results for the last 3 days for most sports.

Moneyline: Compares the winning team to the user's pick.

Updates the bet document to WIN or LOSS

If WIN, atomically increments the user's bankroll by the potential_payout.
