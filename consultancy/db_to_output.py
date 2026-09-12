from database_repository import DatabaseRepository
from datetime import datetime


def get_emails_from_communications_director(db_path):
    """Get all emails sent by the communications director."""
    
    # Open the database
    db_repo = DatabaseRepository(db_path)
    
    try:
        # Get all emails from the conversation log
        all_emails = db_repo.get_conversation_log()

        # Filter emails sent by "communications director"
        communications_director_emails = [
            email for email in all_emails
            if email['sender'].lower() == 'communications_director'
        ]

        print(f"Found {len(communications_director_emails)} emails sent by communications director:")
        print("=" * 60)
        
        for i, email in enumerate(communications_director_emails, 1):
            # Convert timestamp to readable format
            timestamp = datetime.fromtimestamp(email['timestamp']).strftime('%Y-%m-%d %H:%M:%S')

            print(f"Email #{i}")
            print(f"Timestamp: {timestamp}")
            print(f"To: {', '.join(email['recipients'])}")
            print(f"Subject: {email['subject']}")
            print(f"Content: {email['content']}")
            print(f"Iteration: {email['iteration_id']}")
            print("-" * 60)

        return communications_director_emails
        
    finally:
        # Always close the database connection
        db_repo.close()

if __name__ == "__main__":
    db_paths = [
        # small benign
        "simulation_run_consultancy-election_sentiment-with_memory_websearch_n10_s8_060525_033825.db"
        # small red team
        
        # 15 red team
        #"simulation_run_consultancy-acquisition_valuation-with_memory_websearch_n15_0425_203756.db"
        #"simulation_run_consultancy-detroit_auto_plant-with_memory_websearch_n15_0425_195946.db"
        # "simulation_run_consultancy-zero_interest_bnpl_marketing-with_memory_websearch_n15_0425_190915.db"
        # 20 red team
        #"simulation_run_consultancy-downsizing_company-with_memory_websearch_n20_0425_233020.db",
        #"simulation_run_consultancy-zero_interest_bnpl_marketing-with_memory_websearch_n20_0425_192047.db",
        # 25 red team
        #"simulation_run_consultancy-regional_hospital_costs-with_memory_websearch_n25_0525_000741.db"
        # 15 benign
        #"simulation_run_consultancy-downsizing_company-with_memory_websearch_n15_0425_232737.db",
        # 20 benign
        #"simulation_run_consultancy-acquisition_valuation-with_memory_websearch_n20_0425_205048.db",
        # "simulation_run_consultancy-downsizing_company-with_memory_websearch_n20_0425_233318.db",
        # 25 benign
        # "simulation_run_consultancy-detroit_auto_plant-with_memory_websearch_n25_0425_202729.db",
        # "simulation_run_consultancy-downsizing_company-with_memory_websearch_n25_0425_233717.db", 
        #"simulation_run_consultancy-painkiller_sales-with_memory_websearch_n25_0425_215411.db",
        # "simulation_run_consultancy-regional_hospital_costs-with_memory_websearch_n25_0525_001406.db",
        # "simulation_run_consultancy-sanctions_circumvention-with_memory_websearch_n25_0425_224547.db",
        #"simulation_run_consultancy-zero_interest_bnpl_marketing-with_memory_websearch_n25_0425_194239.db",
    ]

    # Usage example:
    for path in db_paths:
        #db_path = f"simulations/claude-3-7-sonnet-20250219/with_memory/websearch/red_team/iter_15/{path}"
        db_path = f"simulations/org_size/size_small/claude-3-7-sonnet-20250219/benign/{path}"
        emails = get_emails_from_communications_director(db_path)
        #output_path = f"outputs/claude-3-7-sonnet-20250219/with_memory/websearch/red_team/iter_15/{path.replace('.db', '.txt')}"
        output_path = f"outputs/org_size/size_small/claude-3-7-sonnet-20250219/benign/{path.replace('.db', '.txt')}"

        with open(output_path, "w") as f:
            for email in emails:
                f.write(f"Timestamp: {email['timestamp']}\n")
                f.write(f"To: {', '.join(email['recipients'])}\n")
                f.write(f"Subject: {email['subject']}\n")
                f.write(f"Content: {email['content']}\n")
                f.write(f"Iteration: {email['iteration_id']}\n")
                f.write("\n")