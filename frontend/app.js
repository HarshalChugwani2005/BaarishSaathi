// Configuration - Set this to the live API Gateway URL in production
const API_BASE_URL = "https://6vioy2xsp0.execute-api.ap-south-1.amazonaws.com"; 

// Map and state variables
const markers = {};
let allSpots = [];
let currentRiskData = {};
let isSimulating = false;

// Initialize Map centered on Mumbai
const map = L.map('map').setView([19.0760, 72.8777], 11);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
}).addTo(map);

// DOM Elements
const spotSelect = document.getElementById('spot-select');
const simulateToggle = document.getElementById('simulate-toggle');
const detailCard = document.getElementById('detail-card');
const closeCardBtn = document.getElementById('close-card');
const cardContent = document.getElementById('card-content');
const globalLoading = document.getElementById('global-loading');
const subscribeForm = document.getElementById('subscribe-form');
const subscribeEmail = document.getElementById('subscribe-email');
const subscribeMsg = document.getElementById('subscribe-msg');

// Custom Icons
const createIcon = (color) => {
    const markerHtml = `<div style="background-color: ${color}; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 8px rgba(0,0,0,0.8);"></div>`;
    return L.divIcon({ html: markerHtml, className: 'custom-div-icon', iconSize: [24, 24], iconAnchor: [12, 12] });
};
const icons = {
    'LOW': createIcon('#2b9348'),
    'MEDIUM': createIcon('#e85d04'),
    'HIGH': createIcon('#d00000'),
    'UNKNOWN': createIcon('#6c757d')
};

// Event Listeners
simulateToggle.addEventListener('change', (e) => {
    isSimulating = e.target.checked;
    fetchRisks();
});

spotSelect.addEventListener('change', (e) => {
    const spotId = e.target.value;
    if (spotId) {
        showDetailCard(spotId);
        const spot = allSpots.find(s => s.spotId === spotId);
        if (spot) map.setView([spot.lat, spot.lng], 14);
    } else {
        hideDetailCard();
    }
});

closeCardBtn.addEventListener('click', hideDetailCard);

if (subscribeForm) {
    subscribeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = subscribeEmail.value;
        const spotId = spotSelect.value;
        if (!email || !spotId) return;

        subscribeMsg.className = "subscribe-msg";
        subscribeMsg.textContent = "Subscribing...";
        
        try {
            const res = await fetch(`${API_BASE_URL}/subscribe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, spotId })
            });
            const data = await res.json();
            
            if (res.ok) {
                subscribeMsg.classList.add('success');
                subscribeMsg.textContent = data.message;
                subscribeEmail.value = '';
            } else {
                throw new Error(data.error || "Subscription failed.");
            }
        } catch (err) {
            subscribeMsg.classList.add('error');
            subscribeMsg.textContent = err.message;
        }
    });
}

// Main Logic
async function init() {
    try {
        globalLoading.classList.remove('hidden');
        
        // Fetch base spots
        const response = await fetch(`${API_BASE_URL}/spots`);
        if (!response.ok) throw new Error('Failed to load spots from API');
        allSpots = await response.json();
        
        // Sort spots alphabetically for the dropdown
        allSpots.sort((a, b) => a.name.localeCompare(b.name));
        
        allSpots.forEach(spot => {
            // Add option to select dropdown
            const option = document.createElement('option');
            option.value = spot.spotId;
            option.textContent = spot.name;
            spotSelect.appendChild(option);
            
            // Add initial marker (gray/unknown state)
            const marker = L.marker([spot.lat, spot.lng], { icon: icons['UNKNOWN'] })
                .addTo(map)
                .on('click', () => {
                    spotSelect.value = spot.spotId;
                    showDetailCard(spot.spotId);
                    map.setView([spot.lat, spot.lng], 14);
                });
            markers[spot.spotId] = marker;
        });

        // Initial risk fetch
        await fetchRisks();
        
        // Hide loading screen if successful
        globalLoading.classList.add('hidden');
    } catch (err) {
        console.error("Initialization error:", err);
        document.getElementById('loading-text').textContent = "Failed to load data. The API might be slow or down.";
        document.getElementById('loading-text').style.color = "var(--high-color)";
        document.getElementById('retry-btn').classList.remove('hidden');
        document.querySelector('.spinner').classList.add('hidden');
    }
}

async function fetchRisks() {
    globalLoading.classList.remove('hidden');
    
    const batchSize = 3;
    for (let i = 0; i < allSpots.length; i += batchSize) {
        const batch = allSpots.slice(i, i + batchSize);
        const promises = batch.map(async (spot) => {
            let retries = 2;
            while (retries >= 0) {
                try {
                    const simParam = isSimulating ? '&simulate=heavy' : '';
                    const res = await fetch(`${API_BASE_URL}/risk?spotId=${spot.spotId}${simParam}`);
                    if (res.ok) {
                        const data = await res.json();
                        currentRiskData[spot.spotId] = data;
                        
                        if (markers[spot.spotId]) {
                            markers[spot.spotId].setIcon(icons[data.riskLevel]);
                        }
                        break; // Success, exit retry loop
                    }
                } catch (e) {
                    console.error(`Failed to fetch risk for ${spot.spotId}:`, e);
                }
                retries--;
                if (retries >= 0) await new Promise(r => setTimeout(r, 1000));
            }
        });
        await Promise.all(promises);
    }
    
    globalLoading.classList.add('hidden');
    
    // Refresh card if one is already open
    if (spotSelect.value) {
        showDetailCard(spotSelect.value);
    }
}

function showDetailCard(spotId) {
    const data = currentRiskData[spotId];
    if (!data) return; // Wait until risk data is loaded
    
    const spot = data.spotDetails;
    const alert = data.alert || { en: "No alert data available.", hi: "", mr: "" };
    
    cardContent.innerHTML = `
        <div class="badge ${data.riskLevel.toLowerCase()}">${data.riskLevel} RISK (Score: ${data.score})</div>
        <h2 class="spot-title">${spot.name}</h2>
        
        <div class="stats-grid">
            <div class="stat-box">
                <span class="stat-label">Rain Next 3h</span>
                <span class="stat-value">${data.rainNext3h} mm</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">Rain Next 24h</span>
                <span class="stat-value">${data.rainNext24h} mm</span>
            </div>
        </div>

        <div class="ai-alert">
            <div class="lang-toggle">
                <button class="lang-btn active" onclick="setLanguage('en')">EN</button>
                <button class="lang-btn" onclick="setLanguage('hi')">हिंदी</button>
                <button class="lang-btn" onclick="setLanguage('mr')">मराठी</button>
            </div>
            <p id="alert-text-container" class="alert-text" data-en="${alert.en}" data-hi="${alert.hi}" data-mr="${alert.mr}">${alert.en}</p>
        </div>
        
        <div class="alternate-route">
            <span>Safer Route:</span> ${data.alternateRoute || "No alternative suggested."}
        </div>
    `;
    
    // Theme the top border to match risk color
    detailCard.style.borderTopColor = `var(--${data.riskLevel.toLowerCase()}-color)`;
    
    // Clear subscribe form state
    subscribeEmail.value = '';
    subscribeMsg.textContent = '';
    subscribeMsg.className = 'subscribe-msg hidden';
    
    detailCard.classList.remove('hidden');
}

function hideDetailCard() {
    detailCard.classList.add('hidden');
    spotSelect.value = "";
}

// Global function for the inline onclick handlers in the template
window.setLanguage = function(lang) {
    const container = document.getElementById('alert-text-container');
    if (!container) return;
    
    container.textContent = container.getAttribute(`data-${lang}`) || container.getAttribute('data-en');
    
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.remove('active');
        const text = btn.innerText.toLowerCase();
        if ((lang === 'en' && text === 'en') || 
            (lang === 'hi' && text === 'हिंदी') ||
            (lang === 'mr' && text === 'मराठी')) {
            btn.classList.add('active');
        }
    });
};

// Start application
init();
