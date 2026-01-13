"""
Progress tracking module for scan operations with ETA calculation.

Provides ScanProgress class to track multi-URL scan progress with:
- Real-time ETA calculation based on average scan time
- Visual progress bar display
- Percentage completion
- Formatted status messages
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScanProgress:
    """
    Track progress of multi-URL scanning operations with ETA estimation.
    
    Attributes:
        total_urls: Total number of URLs to scan
        completed: Number of URLs completed
        start_time: Timestamp when scanning started
        avg_time_per_url: Running average time per URL (seconds)
        current_url: Currently scanning URL (for display)
    """
    total_urls: int
    completed: int = 0
    start_time: float = field(default_factory=time.time)
    avg_time_per_url: float = 3.0  # Initial estimate: 3 seconds per URL
    current_url: Optional[str] = None
    
    def start(self) -> None:
        """Initialize the progress tracker and start timing."""
        self.start_time = time.time()
        self.completed = 0
    
    def update(self, current_url: Optional[str] = None) -> None:
        """
        Update progress after completing a URL scan.
        
        Args:
            current_url: URL currently being scanned (optional)
        """
        self.completed += 1
        elapsed = time.time() - self.start_time
        
        # Calculate running average time per URL
        if self.completed > 0:
            self.avg_time_per_url = elapsed / self.completed
        
        # Update current URL for display
        if current_url:
            self.current_url = current_url
    
    def get_eta_seconds(self) -> int:
        """
        Calculate estimated time remaining in seconds.
        
        Returns:
            Estimated seconds remaining (0 if completed)
        """
        remaining = self.total_urls - self.completed
        if remaining <= 0:
            return 0
        return int(remaining * self.avg_time_per_url)
    
    def get_eta_formatted(self) -> str:
        """
        Get formatted ETA string (e.g., "1m 30s" or "45s").
        
        Returns:
            Human-readable ETA string
        """
        eta = self.get_eta_seconds()
        
        if eta == 0:
            return "Done"
        elif eta < 60:
            return f"{eta}s"
        else:
            minutes = eta // 60
            seconds = eta % 60
            if seconds == 0:
                return f"{minutes}m"
            return f"{minutes}m {seconds}s"
    
    def get_progress_bar(self, width: int = 10, filled_char: str = "█", empty_char: str = "░") -> str:
        """
        Generate a visual progress bar.
        
        Args:
            width: Width of the progress bar in characters
            filled_char: Character for completed portion
            empty_char: Character for remaining portion
            
        Returns:
            Progress bar string
        """
        if self.total_urls == 0:
            return f"[{empty_char * width}]"
        
        filled = int((self.completed / self.total_urls) * width)
        empty = width - filled
        return f"[{filled_char * filled}{empty_char * empty}]"
    
    def get_percentage(self) -> float:
        """
        Get completion percentage.
        
        Returns:
            Percentage complete (0.0 to 100.0)
        """
        if self.total_urls == 0:
            return 100.0
        return (self.completed / self.total_urls) * 100
    
    def format_status(self, include_current: bool = True) -> str:
        """
        Format complete status message with progress bar, percentage, count, and ETA.
        
        Args:
            include_current: Whether to include current URL in status
            
        Returns:
            Formatted status string
        """
        pct = self.get_percentage()
        progress_bar = self.get_progress_bar()
        eta = self.get_eta_formatted()
        
        status = (
            f"{progress_bar} {pct:.0f}%\n"
            f"📊 {self.completed}/{self.total_urls} URLs\n"
            f"⏱️ ETA: {eta}"
        )
        
        if include_current and self.current_url:
            # Truncate URL if too long
            display_url = self.current_url[:30] + "..." if len(self.current_url) > 30 else self.current_url
            status += f"\n\n🔍 {display_url}"
        
        return status
    
    def format_status_boxed(self, include_current: bool = True) -> str:
        """
        Format status with box-drawing characters for better visual appearance.
        
        Args:
            include_current: Whether to include current URL
            
        Returns:
            Formatted status string with box borders
        """
        pct = self.get_percentage()
        progress_bar = self.get_progress_bar()
        eta = self.get_eta_formatted()
        
        status = (
            "╭───────────────────────────╮\n"
            "│   ⏳  SCANNING            │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"{progress_bar} {pct:.0f}%\n"
            f"📊 {self.completed}/{self.total_urls} URLs\n"
            f"⏱️ ETA: {eta}"
        )
        
        if include_current and self.current_url:
            display_url = self.current_url[:30] + "..." if len(self.current_url) > 30 else self.current_url
            status += f"\n\n🔍 {display_url}"
        
        return status
    
    def is_complete(self) -> bool:
        """
        Check if all URLs have been scanned.
        
        Returns:
            True if scanning is complete
        """
        return self.completed >= self.total_urls
    
    def get_elapsed_time(self) -> float:
        """
        Get elapsed time since start in seconds.
        
        Returns:
            Elapsed seconds
        """
        return time.time() - self.start_time
    
    def get_elapsed_formatted(self) -> str:
        """
        Get formatted elapsed time.
        
        Returns:
            Human-readable elapsed time string
        """
        elapsed = int(self.get_elapsed_time())
        
        if elapsed < 60:
            return f"{elapsed}s"
        else:
            minutes = elapsed // 60
            seconds = elapsed % 60
            if seconds == 0:
                return f"{minutes}m"
            return f"{minutes}m {seconds}s"
