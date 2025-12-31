function calculateTimeRemaining(targetTime) {
    const now = new Date();
    const target = new Date(targetTime);
    const diff = target - now;
    
    if (diff <= 0) return null;
    
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    
    if (days > 0) {
        return `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

function formatDateTime(isoString) {
    const date = new Date(isoString);
    const options = {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    };
    return date.toLocaleString('en-US', options);
}

// Update countdown timers
function updateCountdowns() {
    document.querySelectorAll('[data-start-time]').forEach(element => {
        const startTime = element.dataset.startTime;
        const remaining = calculateTimeRemaining(startTime);
        
        if (remaining) {
            element.textContent = remaining;
        } else {
            // Time has passed, reload page to update status
            location.reload();
        }
    });
}

// Run on page load and every minute
document.addEventListener('DOMContentLoaded', function() {
    updateCountdowns();
    setInterval(updateCountdowns, 60000); // Update every minute
    
    const datetimeInputs = document.querySelectorAll('input[type="datetime-local"]');
    datetimeInputs.forEach(input => {
        if (!input.value) {
            const now = new Date();
            now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
            input.value = now.toISOString().slice(0, 16);
        }
    });
});

setTimeout(() => {
    document.querySelectorAll('.flash-messages > div > div').forEach(el => {
        el.style.transition = 'opacity 0.5s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 500);
    });
}, 5000);

document.addEventListener('DOMContentLoaded', function() {
    const datetimeInputs = document.querySelectorAll('input[type="datetime-local"]');
    datetimeInputs.forEach(input => {
        if (!input.value) {
            const now = new Date();
            now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
            input.value = now.toISOString().slice(0, 16);
        }
    });
});