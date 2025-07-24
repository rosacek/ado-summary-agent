"""
Enhanced context builder for hierarchical work item analysis
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class ContextBuilder:
    """Builds hierarchical context from work items and their relationships"""
    
    def __init__(self):
        self.max_context_length = 120000  # Utilize full Phi-3.5 128k context window
        self.response_buffer = 8000  # Reserve space for AI response generation
        
    def build_comprehensive_context(self, primary_item: Dict, linked_items: List[Dict], history: List[Dict] = None) -> str:
        """Build a hierarchical, structured context for AI analysis"""
        
        # Extract core fields efficiently
        fields = primary_item.get('fields', {})
        
        # Build structured sections
        sections = []
        
        # 1. Primary Work Item Context
        sections.append(self._build_primary_context(primary_item))
        
        # 2. Business Context
        sections.append(self._build_business_context(fields))
        
        # 3. Technical Context
        sections.append(self._build_technical_context(fields))
        
        # 4. Relationship Context (summarized)
        if linked_items:
            sections.append(self._build_relationship_context(linked_items))
            
        # 5. Timeline Context (key events only)
        if history:
            sections.append(self._build_timeline_context(history))
            
        # Join and truncate if needed
        full_context = "\n\n".join(sections)
        
        if len(full_context) > self.max_context_length:
            logger.warning(f"Context truncated from {len(full_context)} to {self.max_context_length} chars")
            full_context = full_context[:self.max_context_length]
            
        return full_context
        
    def _build_primary_context(self, work_item: Dict) -> str:
        """Extract essential work item details"""
        fields = work_item.get('fields', {})
        
        return f"""PRIMARY WORK ITEM:
ID: {work_item.get('id', 'Unknown')}
Title: {fields.get('System.Title', '')}
Type: {fields.get('System.WorkItemType', '')}
State: {fields.get('System.State', '')}
Priority: {fields.get('Microsoft.VSTS.Common.Priority', 'Not Set')}
Area: {fields.get('System.AreaPath', '')}

DESCRIPTION:
{self._clean_html(fields.get('System.Description', 'No description'))}

ACCEPTANCE CRITERIA:
{fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', 'Not specified')}"""

    def _build_business_context(self, fields: Dict) -> str:
        """Extract business-relevant information"""
        business_value = fields.get('Microsoft.VSTS.Common.BusinessValue', '')
        tags = fields.get('System.Tags', '')
        
        return f"""BUSINESS CONTEXT:
Business Value: {business_value if business_value else 'Not quantified'}
Tags: {tags if tags else 'None'}
Iteration: {fields.get('System.IterationPath', 'Not assigned')}
Assigned To: {fields.get('System.AssignedTo', {}).get('displayName', 'Unassigned')}"""

    def _build_technical_context(self, fields: Dict) -> str:
        """Extract technical details"""
        return f"""TECHNICAL DETAILS:
Story Points: {fields.get('Microsoft.VSTS.Scheduling.StoryPoints', 'Not estimated')}
Effort: {fields.get('Microsoft.VSTS.Scheduling.Effort', 'Not estimated')}
Reason: {fields.get('System.Reason', 'Standard')}"""

    def _build_relationship_context(self, linked_items: List[Dict]) -> str:
        """Summarize linked work items by relationship type"""
        if not linked_items:
            return "RELATED ITEMS: None"
            
        relationships = {}
        for item in linked_items:
            rel_type = item.get('_relationship', 'Related')
            if rel_type not in relationships:
                relationships[rel_type] = []
                
            item_fields = item.get('fields', {})
            summary = f"{item.get('id')} - {item_fields.get('System.Title', 'Untitled')} ({item_fields.get('System.State', 'Unknown')})"
            relationships[rel_type].append(summary)
            
        context_parts = ["RELATED ITEMS:"]
        for rel_type, items in relationships.items():
            context_parts.append(f"{rel_type}:")
            for item in items[:8]:  # Increased to 8 with maximum context window
                context_parts.append(f"  - {item}")
            if len(items) > 8:
                context_parts.append(f"  - ... and {len(items) - 8} more")
                
        return "\n".join(context_parts)
        
    def _build_timeline_context(self, history: List[Dict]) -> str:
        """Extract key timeline events with expanded context"""
        if not history:
            return "TIMELINE: No history available"
            
        # Focus on significant events - increased with larger context window
        key_events = []
        for event in history[-15:]:  # Increased from 10 to 15 events for richer context
            changed_date = event.get('fields', {}).get('System.ChangedDate', {}).get('newValue', '')
            changed_by = event.get('fields', {}).get('System.ChangedBy', {}).get('newValue', {}).get('displayName', 'Unknown')
            
            # Look for state changes
            if 'System.State' in event.get('fields', {}):
                old_state = event['fields']['System.State'].get('oldValue', '')
                new_state = event['fields']['System.State'].get('newValue', '')
                key_events.append(f"{changed_date}: {changed_by} changed state from '{old_state}' to '{new_state}'")
                
        timeline_text = "TIMELINE:\n" + "\n".join(key_events[-5:]) if key_events else "TIMELINE: No significant state changes"
        return timeline_text
        
    def _clean_html(self, html_content: str) -> str:
        """Clean HTML tags and decode entities with smart truncation"""
        if not html_content:
            return ""
            
        import re
        # Remove HTML tags
        clean_text = re.sub(r'<[^>]+>', '', html_content)
        # Decode common HTML entities
        clean_text = clean_text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        # Normalize whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Smart truncation at sentence boundaries if needed
        max_length = 15000  # Increased limit for richer context
        if len(clean_text) <= max_length:
            return clean_text
            
        # Find last complete sentence within limit
        truncated = clean_text[:max_length]
        last_period = truncated.rfind('.')
        last_exclamation = truncated.rfind('!')
        last_question = truncated.rfind('?')
        
        # Use the latest sentence ending
        sentence_end = max(last_period, last_exclamation, last_question)
        if sentence_end > max_length * 0.8:  # If we found a sentence end in last 20%
            return clean_text[:sentence_end + 1]
        else:
            # Fallback to word boundary
            last_space = truncated.rfind(' ')
            return clean_text[:last_space] + "..." if last_space > 0 else truncated + "..."
