/**
 * Timezone utility functions for client-side timezone handling
 */

const TimezoneUtils = {
    /**
     * Convert a UTC datetime string to the user's local timezone
     * @param {string} utcDateString - UTC datetime string from server
     * @param {string} format - Output format (default: 'YYYY-MM-DD HH:mm')
     * @param {string} targetTimezone - Target timezone (default: business timezone from data attribute)
     * @returns {string} Formatted datetime string in target timezone
     */
    formatDatetime: function(utcDateString, format = 'YYYY-MM-DD HH:mm', targetTimezone = null) {
        if (!utcDateString) return '';
        
        // Get target timezone from data attribute if not specified
        if (!targetTimezone) {
            targetTimezone = document.body.dataset.businessTimezone || 'UTC';
        }
        
        // Parse the UTC date string
        const utcDate = new Date(utcDateString);
        
        // Format options
        const options = {
            timeZone: targetTimezone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        };
        
        try {
            // Format the date in the target timezone
            return new Intl.DateTimeFormat('en-US', options).format(utcDate);
        } catch (error) {
            console.error('Error formatting date:', error);
            return utcDateString; // Return original string if error
        }
    },
    
    /**
     * Initialize timezone display for all elements with data-utc-datetime attribute
     */
    initializeTimezoneDisplay: function() {
        // Get business timezone from body data attribute
        const businessTimezone = document.body.dataset.businessTimezone || 'UTC';
        
        // Find all elements with data-utc-datetime attribute
        const datetimeElements = document.querySelectorAll('[data-utc-datetime]');
        
        datetimeElements.forEach(element => {
            const utcDatetime = element.dataset.utcDatetime;
            const format = element.dataset.format || 'YYYY-MM-DD HH:mm';
            
            // Format the datetime in business timezone
            const localDatetime = this.formatDatetime(utcDatetime, format, businessTimezone);
            
            // Update the element's text content
            element.textContent = localDatetime;
        });
    },
    
    /**
     * Get current time in the business timezone
     * @param {string} targetTimezone - Target timezone
     * @returns {string} Formatted current time string
     */
    getCurrentTimeInTimezone: function(targetTimezone) {
        if (!targetTimezone) {
            targetTimezone = document.body.dataset.businessTimezone || 'UTC';
        }
        
        const now = new Date();
        const options = {
            timeZone: targetTimezone,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        };
        
        try {
            return new Intl.DateTimeFormat('en-US', options).format(now);
        } catch (error) {
            console.error('Error getting current time:', error);
            return now.toLocaleTimeString();
        }
    }
};

// Initialize timezone display when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    TimezoneUtils.initializeTimezoneDisplay();
});
