// Session Timeout Management
// This file handles session timeout warnings and auto-logout functionality

(function() {
    'use strict';

    // Session Configuration
    const SESSION_TIMEOUT = 15 * 60 * 1000; // 15 minutes in milliseconds
    const WARNING_TIME = 13 * 60 * 1000;    // 13 minutes (show warning 2 min before expiry)
    const CHECK_INTERVAL = 1000;            // Check every second

    let sessionTimer;
    let warningTimer;
    let countdownInterval;
    let timeRemaining = SESSION_TIMEOUT;
    let isWarningShown = false;

    // Get URLs from data attributes (set in base.html)
    const body = document.body;
    const keepAliveURL = body.getAttribute('data-keep-alive-url');
    const logoutURL = body.getAttribute('data-logout-url');

    // Reset the session timer
    function resetSessionTimer() {
        // Don't reset if warning is already shown (user must take action)
        if (isWarningShown) return;

        timeRemaining = SESSION_TIMEOUT;
        console.log('Session timer reset. Time remaining:', formatTime(timeRemaining));
    }

    // Format milliseconds to MM:SS
    function formatTime(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    // Show warning modal
    function showWarningModal() {
        isWarningShown = true;
        const modal = document.getElementById('sessionWarningModal');
        if (modal) {
            modal.classList.remove('hidden');

            // Start countdown
            const warningTimeLeft = SESSION_TIMEOUT - WARNING_TIME;
            let countdown = warningTimeLeft;

            updateCountdown(countdown);

            countdownInterval = setInterval(() => {
                countdown -= 1000;
                updateCountdown(countdown);

                if (countdown <= 0) {
                    clearInterval(countdownInterval);
                    logoutNow();
                }
            }, 1000);
        }
    }

    // Update countdown display
    function updateCountdown(ms) {
        const countdownElement = document.getElementById('sessionCountdown');
        if (countdownElement) {
            countdownElement.textContent = formatTime(ms);
        }
    }

    // Hide warning modal
    function hideWarningModal() {
        isWarningShown = false;
        const modal = document.getElementById('sessionWarningModal');
        if (modal) {
            modal.classList.add('hidden');
        }

        if (countdownInterval) {
            clearInterval(countdownInterval);
        }
    }

    // Extend session
    function extendSession() {
        fetch(keepAliveURL)
            .then(response => {
                if (response.ok) {
                    console.log('Session extended.');
                    hideWarningModal();
                    resetSessionTimer();
                } else {
                    console.error('Failed to extend session.');
                }
            })
            .catch(error => {
                console.error('Error extending session:', error);
            });
    }

    // Logout immediately
    function logoutNow() {
        window.location.href = logoutURL;
    }

    // Activity detected handler
    function activityDetected() {
        resetSessionTimer();
    }

    // Main session timer
    function startSessionTimer() {
        sessionTimer = setInterval(() => {
            timeRemaining -= CHECK_INTERVAL;

            // Show warning when time reaches WARNING_TIME
            if (timeRemaining <= WARNING_TIME && !isWarningShown) {
                showWarningModal();
            }

            // Auto logout when time expires
            if (timeRemaining <= 0 && !isWarningShown) {
                clearInterval(sessionTimer);
                logoutNow();
            }
        }, CHECK_INTERVAL);
    }

    // Desktop events
    window.addEventListener('mousemove', activityDetected, { passive: true });
    window.addEventListener('keydown', activityDetected, { passive: true });
    window.addEventListener('scroll', activityDetected, { passive: true });
    window.addEventListener('click', activityDetected, { passive: true });

    // Touch/Mobile events
    window.addEventListener('touchstart', activityDetected, { passive: true });
    window.addEventListener('touchmove', activityDetected, { passive: true });
    window.addEventListener('touchend', activityDetected, { passive: true });

    // Start the session timer
    startSessionTimer();
    console.log('Session timeout initialized: 15 minutes (warning at 13 minutes)');

    // Expose functions globally for onclick handlers
    window.extendSession = extendSession;
    window.logoutNow = logoutNow;

})();
