import os
import re
import logging
from datetime import datetime, timedelta
import textwrap
import time
from .settings import WORK_ITEM_IDS, ADO_URL, ADO_PROJECT_NAME, ADO_PAT
from .ado_client import ADOClient
from .summarizer import Summarizer
from .context_builder import ContextBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class Agent:
    def __init__(self, ado_client=None, summarizer=None):
        # Initialize components, using defaults if not provided
        self.ado_client = ado_client or ADOClient(
            ADO_URL.split("/")[-1], ADO_PROJECT_NAME, ADO_PAT or None
        )
        self.summarizer = summarizer or Summarizer()
        self.context_builder = ContextBuilder()
        self.start_time = None
        self.processed_times = []

    def fetch_work_items(self):
        # Fetch by explicit IDs, fallback to dummy items if none retrieved
        logging.info("Fetching work items...")
        items = self.ado_client.get_work_items(WORK_ITEM_IDS)
        if not items:
            items = [
                {"id": wid, "fields": {"System.Title": f"Work Item {wid}"}}
                for wid in WORK_ITEM_IDS
            ]
        logging.info(f"Retrieved {len(items)} work items: {[item.get('id') for item in items]}")
        return items

    def run(self):
        # Log AI model availability
        logging.info(f"AI model available: {self.summarizer.is_available()}")

        work_items = self.fetch_work_items()
        
        # Separate primary work items from linked ones
        primary_items = [item for item in work_items if '_relationship' not in item]
        linked_items = [item for item in work_items if '_relationship' in item]

        # Process ALL work items without prioritization
        logging.info(f"📊 Processing {len(primary_items)} work items in original order (no prioritization)")

        # Group linked items by primary work item ID
        linked_by_primary = {}
        for item in linked_items:
            rel_id = item.get('relations', [{}])[0].get('target', None) if item.get('relations') else None
            if not rel_id:
                rel_id = item.get('fields', {}).get('System.Parent', None)
            if rel_id:
                linked_by_primary.setdefault(rel_id, []).append(item)

        summaries = []
        total = len(primary_items)
        self.start_time = datetime.now()

        # Process work items in their original order (no prioritization)
        for idx, primary_item in enumerate(primary_items, start=1):
            item_id = primary_item.get('id')
            title = primary_item.get('fields', {}).get('System.Title', 'N/A')
            logging.info(f"Processing work item {idx}/{total}: {item_id} - {title}")

            start_item_time = datetime.now()
            # Get all linked items for this primary item
            linked_context_items = linked_by_primary.get(item_id, [])

            # Use ContextBuilder for comprehensive context extraction
            primary_history = self.ado_client.get_work_item_history(item_id)
            full_context = self.context_builder.build_comprehensive_context(
                primary_item=primary_item,
                linked_items=linked_context_items,
                history=primary_history
            )

            # Prepare to generate summary with enhanced retry logic
            MAX_RETRIES = 5  # Increased retries for connection issues
            RETRY_DELAY = 10  # Longer delay for model stability
            summary_start_time = datetime.now()
            summary = None
            last_exception = None
            
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logging.info(f"🔄 Attempt {attempt}/{MAX_RETRIES} to generate AI summary for work item {item_id}")
                    summary = self.summarizer.summarize(full_context)
                    logging.info(f"✅ AI summary generated successfully on attempt {attempt}")
                    break
                except Exception as e:
                    last_exception = e
                    logging.warning(f"❌ Attempt {attempt}/{MAX_RETRIES} failed for work item {item_id}: {e}")
                    if attempt < MAX_RETRIES:
                        logging.info(f"⏳ Retrying in {RETRY_DELAY}s...")
                        time.sleep(RETRY_DELAY)
                        # Exponential backoff for connection issues
                        if "disconnected" in str(e).lower() or "connection" in str(e).lower():
                            RETRY_DELAY *= 1.5  # Increase delay for connection issues
            
            # If all retries failed, fail the entire process
            if summary is None:
                err = str(last_exception) if last_exception else 'Unknown error'
                error_msg = f"🚫 CRITICAL: Failed to generate AI summary for work item {item_id} after {MAX_RETRIES} attempts: {err}"
                logging.error(error_msg)
                logging.error("🛑 Aborting process - all work items must be processed with AI")
                raise RuntimeError(f"AI summarization failed after {MAX_RETRIES} attempts for work item {item_id}: {err}")

            # Format successful summary with improved readability
            try:
                summary_time = (datetime.now() - summary_start_time).total_seconds()
                logging.info(f"⏱️  Summary generation took {summary_time:.1f} seconds")
                
                # Detect likely truncation (ends mid-section or mid-sentence)
                truncation_markers = [
                    '⚠️ **RISKS & DEPENDENCIES**',
                    '⚡ **EXECUTION PLAN**',
                    '💰 **EXPECTED IMPACT/ROI**',
                    '🚀 **FUTURE STATE**',
                    '📊 **CURRENT STATE**',
                    '🎯 **PROBLEM STATEMENT**'
                ]
                is_truncated = any(summary.strip().endswith(marker) for marker in truncation_markers) or summary.strip().endswith(':')
                if is_truncated:
                    summary = summary.strip() + '\n[Summary truncated due to length limitations. Please review the full work item for complete details.]'
                
                # Enhanced formatting for better readability
                formatted_summary = self._format_summary_for_readability(summary, item_id, title)
                summaries.append(formatted_summary)
                
            except Exception as e:
                logging.error(f"Unexpected formatting error for work item {item_id}: {e}")
                # Fallback to basic formatting if advanced formatting fails
                basic_formatted = (
                    f"\n{'='*100}\n"
                    f"Work Item {item_id}: {title}\n"
                    f"{'='*100}\n\n"
                    f"{summary}\n"
                )
                summaries.append(basic_formatted)
                # handle formatting errors similar to summarization errors
                error_summary = (
                    f"\n{'-'*100}\n"
                    f"Work Item {item_id}: {title}\n"
                    f"{'-'*100}\n\n"
                    f"❌ **ERROR FORMATTING WORK ITEM SUMMARY**\n\n"
                    f"Formatting failed: {e}\n"
                )
                summaries.append(error_summary)

            # record processing time and estimated remaining
            elapsed_time = (datetime.now() - start_item_time).total_seconds()
            self.processed_times.append(elapsed_time)
            if idx > 1:
                avg_time = sum(self.processed_times) / len(self.processed_times)
                remaining = total - idx
                estimated_time = avg_time * remaining
                logging.info(f"Estimated time remaining for {remaining} items: approx {estimated_time / 60:.2f} minutes")
        # end for
        
        # Create final summary with clean markdown structure
        final_report = f"""# ADO Work Items Summary Report
*Generated on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}*

**Items Processed**: {total}  
**Success Rate**: {len([s for s in summaries if '❌' not in s])}/{total}  
**Total Time**: {(datetime.now() - self.start_time).total_seconds() / 60:.1f} minutes

---

{"".join(summaries)}

---

*End of Report*
"""
        return final_report

    def _build_linked_context(self, linked_items):
        """Build context from linked items grouped by relationship"""
        # For now, return all linked items as general context
        # In a more sophisticated implementation, we'd group by primary item ID
        return {"general": linked_items}

    def _create_management_summary(self, work_item, linked_context):
        """Generate a concise, executive summary for Product Management that includes:
            - The business problem and its impact
            - Key technical details and technologies involved
            - Main features and development work required
            - Current status and blockers
            - Actionable next steps or recommendations
        Base the summary on the full work item description and all available fields. Avoid generic statements; use specific details from the context. Format for easy copy-paste into reports."""
        
        work_item_id = work_item.get("id", "Unknown ID")
        work_item_title = work_item.get("fields", {}).get("System.Title", "No Title")
        work_item_description = work_item.get("fields", {}).get("System.Description", "No Description")

        # Extract relevant details from the work item
        technologies = self._extract_field(work_item_description, "Technologies")
        features = self._extract_field(work_item_description, "Features")
        development_work = self._extract_field(work_item_description, "Development Work")

        # Clean the description for summary use
        clean_description = self._clean_html(work_item_description)
        summary_body = ""
        if technologies or features or development_work:
            if technologies:
                summary_body += f"Technologies: {technologies}\n"
            if features:
                summary_body += f"Features: {features}\n"
            if development_work:
                summary_body += f"Development Work: {development_work}\n"
        else:
            # If no labeled fields, use the cleaned description as the summary
            summary_body = f"Summary: {clean_description}\n"

        # Add linked context if available
        linked_summary = ""
        if linked_context:
            linked_summary = self._summarize_linked_context(linked_context)
            if linked_summary:
                summary_body += f"Linked Items: {linked_summary}\n"

        summary = f"Work Item {work_item_id}: {work_item_title}\n{summary_body}"
        return summary.strip()

    def _extract_field(self, text, field_name):
        """Extract specific field details from the text."""
        # Improved logic for extracting field details
        pattern = rf"{field_name}:\s*(.*?)\s*(\n|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _summarize_linked_context(self, linked_context):
        """Summarize linked work items."""
        summaries = []
        for linked_item in linked_context:
            linked_id = linked_item.get("id", "Unknown ID")
            linked_title = linked_item.get("fields", {}).get("System.Title", "No Title")
            summaries.append(f"{linked_id}: {linked_title}")
        return ", ".join(summaries)

    def _clean_html(self, html_content):
        """Remove HTML tags and clean up content"""
        if not html_content:
            return ""
        
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', html_content)
        # Replace HTML entities
        clean = clean.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        # Clean up whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _summarize_linked_context(self, linked_context):
        """Create a detailed summary of linked work items for context"""
        if not linked_context or not linked_context.get("general"):
            return "No linked work items for additional context."
        
        linked_items = linked_context["general"]
        context_summary = []
        
        # Group by relationship type
        relationships = {}
        for item in linked_items:
            fields = item.get('fields', {})
            title = self._clean_html(fields.get('System.Title', 'Untitled'))
            state = fields.get('System.State', 'Unknown')
            rel_type = item.get('_relationship', 'Related')
            
            if rel_type not in relationships:
                relationships[rel_type] = []
            relationships[rel_type].append(f"{title} ({state})")
        
        # Format by relationship type
        for rel_type, items in relationships.items():
            rel_display = rel_type.replace('System.LinkTypes.', '').replace('-', ' ')
            context_summary.append(f"\n{rel_display}:")
            for item in items[:3]:  # Show up to 3 per type
                context_summary.append(f"  • {item}")
            if len(items) > 3:
                context_summary.append(f"  • ... and {len(items) - 3} more")
            
        return "\n".join(context_summary) if context_summary else "No linked work items for additional context."

    def _extract_work_item_context(self, work_item, history=None):
        """Extract key information from work item for summarization, including history/discussion if provided"""
        if not isinstance(work_item, dict):
            return str(work_item)
        fields = work_item.get('fields', {})
        
        # Extract comprehensive work item details
        title = fields.get('System.Title', 'No title')
        description = self._clean_html(fields.get('System.Description', ''))
        state = fields.get('System.State', 'Unknown')
        work_item_type = fields.get('System.WorkItemType', 'Unknown')
        assigned_to = fields.get('System.AssignedTo', {}).get('displayName', 'Unassigned')
        area_path = fields.get('System.AreaPath', '')
        tags = fields.get('System.Tags', '')
        priority = fields.get('Microsoft.VSTS.Common.Priority', 'Not Set')
        
        # Business value and impact fields
        business_value = fields.get('Microsoft.VSTS.Common.BusinessValue', '')
        effort = fields.get('Microsoft.VSTS.Scheduling.Effort', '')
        story_points = fields.get('Microsoft.VSTS.Scheduling.StoryPoints', '')
        
        # Dates - format them nicely
        created_date = self._format_date(fields.get('System.CreatedDate', ''))
        target_date = self._format_date(fields.get('Microsoft.VSTS.Scheduling.TargetDate', ''))
        due_date = self._format_date(fields.get('Microsoft.VSTS.Scheduling.DueDate', ''))
        
        # Acceptance criteria and other details
        acceptance_criteria = self._clean_html(fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', ''))
        reason = fields.get('System.Reason', '')
        
        # Check if this is a linked work item
        relationship = work_item.get('_relationship', '')
        relationship_context = f" (Linked as: {relationship})" if relationship else ""
        
        # Create a concise, labeled context for AI summarization
        parts = []
        parts.append(f"ID: {work_item.get('id', 'Unknown')}")
        parts.append(f"Title: {fields.get('System.Title', '')}")
        parts.append(f"Type: {fields.get('System.WorkItemType', '')}")
        parts.append(f"State: {fields.get('System.State', '')}")
        parts.append(f"Priority: {fields.get('Microsoft.VSTS.Common.Priority', '')}")
        parts.append(f"Business Value: {fields.get('Microsoft.VSTS.Common.BusinessValue', '')}")
        # Include description and acceptance criteria explicitly
        parts.append("Description:\n" + self._clean_html(fields.get('System.Description', '')).strip())
        parts.append("Acceptance Criteria:\n" + fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', '').strip())
        # Optionally include history
        if history:
            parts.append(self._format_history(history))  # Now includes its own header
        # Return structured context
        return "\n\n".join(parts)

    def _format_date(self, date_string):
        """Format ISO date strings to readable format"""
        if not date_string:
            return ""
        try:
            # Parse ISO format date
            dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return date_string

    def _format_history(self, history):
        """Format the work item update history for summarization context, filtering for last 3 months."""
        if not history:
            return ''
        
        # Calculate the cutoff date (3 months ago)
        three_months_ago = datetime.now() - timedelta(days=90)
        
        history_lines = []
        for update in history:
            rev = update.get('rev', '')
            changed_by = update.get('revisedBy', {}).get('displayName', '')
            changed_date_str = update.get('revisedDate', '')
            fields = update.get('fields', {})
            comments = update.get('fields', {}).get('System.History', {}).get('newValue', '')
            
            # Parse and filter by date (only include last 3 months)
            if changed_date_str:
                try:
                    # Parse the date string (assuming ISO format from Azure DevOps)
                    # Remove timezone info if present and parse
                    date_clean = changed_date_str.split('T')[0] if 'T' in changed_date_str else changed_date_str
                    if '.' in changed_date_str:
                        # Handle format like "2024-01-15T10:30:45.123Z"
                        changed_date = datetime.fromisoformat(changed_date_str.replace('Z', '+00:00'))
                    else:
                        # Handle simpler formats
                        changed_date = datetime.fromisoformat(changed_date_str.replace('Z', ''))
                    
                    # Skip updates older than 3 months
                    if changed_date.replace(tzinfo=None) < three_months_ago:
                        continue
                except (ValueError, AttributeError):
                    # If date parsing fails, include the update to be safe
                    logging.warning(f"Could not parse date: {changed_date_str}")
            
            # Summarize field changes
            field_changes = []
            for field, change in fields.items():
                if field == 'System.History':
                    continue
                old = change.get('oldValue', '')
                new = change.get('newValue', '')
                if old != new:
                    field_changes.append(f"{field}: '{old}' → '{new}'")
            
            line = f"[{changed_date_str}] {changed_by}: "
            if comments:
                line += f"Comment: {self._clean_html(comments)} "
            if field_changes:
                line += f"Changes: {', '.join(field_changes)}"
            if line.strip() != f"[{changed_date_str}] {changed_by}:":
                history_lines.append(line.strip())
        
        # Return recent history (last 15 updates instead of 10 since we're filtering by date now)
        recent_history = '\n'.join(history_lines[-15:]) if history_lines else ''
        
        # Add a note about the time filter
        if recent_history:
            return f"Recent Activity (Last 3 Months):\n{recent_history}"
        else:
            return "Recent Activity (Last 3 Months): No recent updates found."
    
    def _format_summary_for_readability(self, summary, item_id, title):
        """Format summary with clean, professional markdown structure"""
        
        # Clean title and create proper header
        title_clean = self._clean_title(title)
        header = f"""# Work Item {item_id}: {title_clean}

"""
        
        # Process and clean the summary content
        formatted_content = self._clean_summary_content(summary)
        
        # Add clean separator
        footer = f"""

---

"""
        
        return header + formatted_content + footer
    
    def _clean_title(self, title):
        """Clean title for readability without truncation"""
        # Remove extra brackets and clean up
        title = re.sub(r'\[([^\]]+)\]\s*', '', title)  # Remove [prefix] patterns
        title = title.strip()
        
        # No truncation - keep full title for context
        return title
    
    def _clean_summary_content(self, summary):
        """Clean and format AI summary content with consistent structure"""
        lines = summary.split('\n')
        clean_lines = []
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines - we'll add them strategically
            if not line:
                continue
                
            # Skip AI instruction artifacts
            if self._is_instruction_artifact(line):
                continue
                
            # Handle section headers
            if line.startswith('**') and line.endswith('**'):
                section_name = line.strip('*').strip()
                if self._is_valid_section(section_name):
                    # Add spacing before new sections
                    if clean_lines and clean_lines[-1] != "":
                        clean_lines.append("")
                    clean_lines.append(f"## {section_name}")
                    clean_lines.append("")
                    current_section = section_name.lower()
                continue
            
            # Format content based on section
            if current_section:
                formatted_line = self._format_section_content(line, current_section)
                if formatted_line:
                    clean_lines.append(formatted_line)
        
        return '\n'.join(clean_lines)
    
    def _is_instruction_artifact(self, line):
        """Check if line is an AI instruction artifact to remove"""
        artifacts = [
            'STRICT RULES:', 'OUTPUT FORMAT', 'RULES:', 'Use ONLY', 
            'exact field values', 'Copy field values', 'No assumptions',
            '[exact ID]', '[exact type]', '[exact state]', '[Copy description',
            'based on title and description only'
        ]
        return any(artifact in line for artifact in artifacts)
    
    def _is_valid_section(self, section_name):
        """Check if section is a valid summary section"""
        valid_sections = [
            'executive summary', 'key details', 'description', 
            'acceptance criteria', 'technical details', 'next actions',
            'dependencies', 'risks', 'dependencies & risks'
        ]
        return section_name.lower() in valid_sections
    
    def _format_section_content(self, line, section):
        """Format content based on the section type"""
        
        # Handle bullet points consistently
        if line.startswith('•') or line.startswith('-'):
            # Clean up bullet formatting
            content = line.lstrip('•- ').strip()
            if content:
                return f"- {content}"
            return None
            
        # Handle key details section specially
        if section == 'key details':
            # Clean up field formatting (Work Item ID: 123456)
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    field = parts[0].strip()
                    value = parts[1].strip()
                    # Remove artifacts like [exact ID] etc
                    value = re.sub(r'\[exact [^\]]+\]', '', value).strip()
                    if value and value not in ['Not specified', 'Not provided']:
                        return f"- **{field}**: {value}"
                    else:
                        return f"- **{field}**: Not specified"
            return None
            
        # Handle regular content with proper line length
        if len(line) > 90:
            wrapped = textwrap.fill(line, width=90, 
                                  break_long_words=False, 
                                  break_on_hyphens=False)
            return wrapped
        else:
            return line
