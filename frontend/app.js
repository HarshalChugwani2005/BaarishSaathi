// Configuration
const API_BASE_URL = "https://6vioy2xsp0.execute-api.ap-south-1.amazonaws.com"; 

// Map and state variables
const markers = {};
let allSpots = [];
let currentRiskData = {};
let isSimulating = false;
let currentSelectedSpot = null;

// Initialize Map
const map = L.map('map', {zoomControl: false}).setView([19.0760, 72.8777], 11);
L.control.zoom({ position: 'bottomright' }).addTo(map);

// Using standard OSM basemap since Carto now requires an API key
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
}).addTo(map);

// DOM Elements
const spotSelect = document.getElementById('spot-select');
const simulateToggle = document.getElementById('simulate-toggle');
const bottomSheet = document.getElementById('bottom-sheet');
const closeCardBtn = document.getElementById('close-card');
const cardContent = document.getElementById('card-content');
const globalLoading = document.getElementById('global-loading');
const subscribeForm = document.getElementById('subscribe-form');
const subscribeEmail = document.getElementById('subscribe-email');
const subscribeSection = document.getElementById('subscribe-section');
const spotListContainer = document.getElementById('spot-list');
const cardTitle = document.getElementById('card-title');
const cardBadge = document.getElementById('card-badge');
const sheetHandleArea = document.getElementById('sheet-handle-area');

// Custom Icons
const createIcon = (level) => {
    const levelClass = level.toLowerCase();
    const markerHtml = `<div class="marker-pin ${levelClass}"></div>`;
    return L.divIcon({ html: markerHtml, className: 'custom-div-icon', iconSize: [22, 22], iconAnchor: [11, 11] });
};

// Event Listeners
simulateToggle.addEventListener('change', (e) => {
    isSimulating = e.target.checked;
    fetchRisks();
});

if (spotSelect) {
    spotSelect.addEventListener('change', (e) => {
        if (e.target.value) {
            selectSpot(e.target.value);
        } else {
            hideDetailCard();
        }
    });
}

if (closeCardBtn) closeCardBtn.addEventListener('click', hideDetailCard);

if (subscribeForm) {
    subscribeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = subscribeEmail.value;
        const spotId = currentSelectedSpot;
        if (!email || !spotId) return;

        const btn = subscribeForm.querySelector('button');
        btn.textContent = "Subscribing...";
        btn.disabled = true;
        
        try {
            const res = await fetch(`${API_BASE_URL}/subscribe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, spotId })
            });
            const data = await res.json();
            
            if (res.ok) {
                showToast(data.message, 'success');
                subscribeEmail.value = '';
            } else {
                throw new Error(data.error || "Subscription failed.");
            }
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            btn.textContent = "Subscribe";
            btn.disabled = false;
        }
    });
}

// Bottom Sheet Logic for Mobile
let startY = 0;
let currentTranslate = 0;
const PEEK = 22;
const HALF = 50;
const FULL = 85;

function setSheetState(state) {
    bottomSheet.className = 'bottom-sheet'; // clear previous states
    if (state === 'hidden') bottomSheet.classList.add('sheet-hidden');
    else if (state === 'peek') bottomSheet.classList.add('sheet-peek');
    else if (state === 'half') bottomSheet.classList.add('sheet-half');
    else if (state === 'full') bottomSheet.classList.add('sheet-full');
}

sheetHandleArea.addEventListener('touchstart', e => {
    startY = e.touches[0].clientY;
}, {passive: true});

sheetHandleArea.addEventListener('touchend', e => {
    const endY = e.changedTouches[0].clientY;
    const delta = startY - endY; // positive = dragged up
    
    if (bottomSheet.classList.contains('sheet-peek')) {
        if (delta > 30) setSheetState('half');
    } else if (bottomSheet.classList.contains('sheet-half')) {
        if (delta > 30) setSheetState('full');
        if (delta < -30) setSheetState('peek');
    } else if (bottomSheet.classList.contains('sheet-full')) {
        if (delta < -30) setSheetState('half');
    }
});
sheetHandleArea.addEventListener('click', () => {
    if (bottomSheet.classList.contains('sheet-peek')) setSheetState('half');
    else if (bottomSheet.classList.contains('sheet-half')) setSheetState('full');
    else if (bottomSheet.classList.contains('sheet-full')) setSheetState('half');
});


// Main Logic
async function init() {
    try {
        globalLoading.classList.remove('hidden');
        
        const response = await fetch(`${API_BASE_URL}/spots`);
        if (!response.ok) throw new Error('Failed to load spots from API');
        allSpots = await response.json();
        
        allSpots.sort((a, b) => a.name.localeCompare(b.name));
        
        allSpots.forEach(spot => {
            if (spotSelect) {
                const option = document.createElement('option');
                option.value = spot.spotId;
                option.textContent = spot.name;
                spotSelect.appendChild(option);
            }
            
            const marker = L.marker([spot.lat, spot.lng], { icon: createIcon('unknown') })
                .addTo(map)
                .on('click', () => selectSpot(spot.spotId));
            markers[spot.spotId] = marker;
        });

        renderSpotList(allSpots);
        await fetchRisks();
        
        globalLoading.classList.add('hidden');
    } catch (err) {
        console.error("Init error:", err);
        document.getElementById('loading-text').textContent = "Couldn't load map data. Please check your connection.";
        document.getElementById('loading-text').style.color = "var(--high-color)";
        document.getElementById('retry-btn').classList.remove('hidden');
        document.querySelector('.spinner').classList.add('hidden');
    }
}

async function fetchRisks() {
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
                            markers[spot.spotId].setIcon(createIcon(data.riskLevel));
                        }
                        break; 
                    }
                } catch (e) {
                    console.error(`Failed risk for ${spot.spotId}:`, e);
                }
                retries--;
                if (retries >= 0) await new Promise(r => setTimeout(r, 1000));
            }
        });
        await Promise.all(promises);
    }
    
    // Update sidebar list sorting based on new risk data
    const sortedSpots = [...allSpots].sort((a, b) => {
        const scoreA = currentRiskData[a.spotId]?.score || 0;
        const scoreB = currentRiskData[b.spotId]?.score || 0;
        return scoreB - scoreA;
    });
    renderSpotList(sortedSpots);
    
    if (currentSelectedSpot) {
        renderDetailCard(currentSelectedSpot);
    }
}

function renderSpotList(spots) {
    if (!spotListContainer) return;
    spotListContainer.innerHTML = '';
    spots.forEach(spot => {
        const data = currentRiskData[spot.spotId];
        const riskLevel = data ? data.riskLevel.toLowerCase() : 'unknown';
        const score = data ? data.score : '-';
        
        const item = document.createElement('div');
        item.className = `spot-list-item ${currentSelectedSpot === spot.spotId ? 'selected' : ''}`;
        item.onclick = () => selectSpot(spot.spotId);
        item.innerHTML = `
            <div class="spot-item-info">
                <h4>${spot.name}</h4>
                <p>${spot.area}</p>
            </div>
            <div class="badge ${riskLevel}">
                ${riskLevel === 'high' ? '<span class="badge-icon high"></span>' : (riskLevel === 'medium' ? '<span class="badge-icon medium"></span>' : '<span class="badge-icon low"></span>')}
                ${score}
            </div>
        `;
        spotListContainer.appendChild(item);
    });
}

function selectSpot(spotId) {
    if (currentSelectedSpot && markers[currentSelectedSpot]) {
        const oldIcon = markers[currentSelectedSpot].getIcon();
        const div = markers[currentSelectedSpot].getElement();
        if(div && div.children[0]) div.children[0].classList.remove('selected');
    }
    
    currentSelectedSpot = spotId;
    if (spotSelect) spotSelect.value = spotId;
    
    const spot = allSpots.find(s => s.spotId === spotId);
    if (spot) {
        // Pan map keeping marker visible above bottom sheet on mobile
        if (window.innerWidth < 900) {
            map.setView([spot.lat - 0.02, spot.lng], 13);
        } else {
            map.setView([spot.lat, spot.lng], 14);
        }
    }
    
    if (markers[spotId]) {
        const div = markers[spotId].getElement();
        if(div && div.children[0]) div.children[0].classList.add('selected');
    }
    
    renderSpotList(allSpots); // update selection outline
    renderDetailCard(spotId);
    
    if (window.innerWidth < 900) {
        setSheetState('peek');
    } else {
        bottomSheet.classList.remove('sheet-hidden');
    }
}

function renderDetailCard(spotId) {
    const spot = allSpots.find(s => s.spotId === spotId);
    if (!spot) return;
    
    cardTitle.textContent = spot.name;
    const data = currentRiskData[spotId];
    
    if (!data) {
        // Skeleton state
        cardBadge.className = 'badge unknown';
        cardBadge.innerHTML = 'Loading...';
        subscribeSection.classList.add('hidden');
        cardContent.innerHTML = `
            <div class="stats-grid">
                <div class="stat-box skeleton"><div class="sk-title"></div><div class="sk-text"></div></div>
                <div class="stat-box skeleton"><div class="sk-title"></div><div class="sk-text"></div></div>
            </div>
            <div class="skeleton" style="height: 100px; margin-bottom: 16px; border-radius: 12px;"></div>
            <div class="skeleton" style="height: 48px; border-radius: 8px;"></div>
        `;
        return;
    }
    
    const rLevel = data.riskLevel.toLowerCase();
    let iconHtml = rLevel === 'high' ? '<span class="badge-icon high"></span>' : (rLevel === 'medium' ? '<span class="badge-icon medium"></span>' : '<span class="badge-icon low"></span>');
    cardBadge.className = `badge ${rLevel}`;
    cardBadge.innerHTML = `${iconHtml} ${data.riskLevel}`;
    
    const alert = data.alert || { en: "No alert data available.", hi: "", mr: "" };
    
    // Calculate bar widths relative to a heavy rain threshold (e.g. 50mm 3h, 200mm 24h max visual)
    const pct3h = Math.min(100, (data.rainNext3h / 50) * 100);
    const pct24h = Math.min(100, (data.rainNext24h / 200) * 100);
    const scorePct = data.score;
    
    cardContent.innerHTML = `
        <div class="score-gauge">
            <div class="score-header">
                <span>Risk Score</span>
                <span>${data.score}/100</span>
            </div>
            <div class="score-track">
                <div class="score-marker" style="left: ${scorePct}%"></div>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <span class="stat-label">Next 3 Hours</span>
                <span class="stat-value">${data.rainNext3h}<span style="font-size:12px;font-weight:400;margin-left:2px">mm</span></span>
                <div class="stat-bar"><div class="stat-bar-fill" style="width: ${pct3h}%"></div></div>
            </div>
            <div class="stat-box">
                <span class="stat-label">Next 24 Hours</span>
                <span class="stat-value">${data.rainNext24h}<span style="font-size:12px;font-weight:400;margin-left:2px">mm</span></span>
                <div class="stat-bar"><div class="stat-bar-fill" style="width: ${pct24h}%"></div></div>
            </div>
        </div>

        ${data.tide ? `
        <div class="tide-block">
            <div class="tide-header">
                <span class="tide-title">High Tide</span>
                ${data.tide.coincidesWithRain ? '<div class="tide-overlap-chip">⚠️ Rain + high tide overlap</div>' : ''}
            </div>
            <div class="tide-info">
                Next peak at <strong>${data.tide.nextHighTideTime}</strong> (${data.tide.nextHighTideHeight}m)
            </div>
            <div class="mini-timeline-container">
                <svg viewBox="0 0 240 80" width="100%" height="100%" preserveAspectRatio="none">
                    ${data.tide.coincidesWithRain ? '<rect x="30" y="0" width="40" height="80" fill="var(--high-bg)" opacity="0.5" />' : ''}
                    <!-- Mock Rain Bars -->
                    <rect x="10" y="50" width="15" height="30" fill="var(--accent)" opacity="0.3" rx="2" />
                    <rect x="35" y="${data.tide.coincidesWithRain ? '20' : '60'}" width="15" height="${data.tide.coincidesWithRain ? '60' : '20'}" fill="var(--accent)" rx="2" />
                    <rect x="60" y="55" width="15" height="25" fill="var(--accent)" opacity="0.5" rx="2" />
                    <!-- Mock Tide Curve -->
                    <path d="M0,60 Q40,${data.tide.coincidesWithRain ? '10' : '50'} 80,60 T160,60 T240,60" fill="none" stroke="var(--text-main)" stroke-width="2" />
                </svg>
            </div>
        </div>
        ` : ''}

        <div class="ai-alert">
            <div class="lang-toggle">
                <button class="lang-btn active" onclick="setLanguage('en')" aria-label="English">EN</button>
                <button class="lang-btn" onclick="setLanguage('hi')" aria-label="Hindi">हिंदी</button>
                <button class="lang-btn" onclick="setLanguage('mr')" aria-label="Marathi">मराठी</button>
            </div>
            <p id="alert-text-container" class="alert-text" aria-live="polite" data-en="${alert.en}" data-hi="${alert.hi}" data-mr="${alert.mr}">${alert.en}</p>
        </div>
        
        <div class="alternate-route">
            <svg class="route-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 20v-4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v4"/><path d="M12 2L2 12h3v8h14v-8h3L12 2z"/></svg>
            <div>
                <strong style="display:block;font-size:12px;color:var(--text-muted);margin-bottom:2px">Safer Route</strong>
                ${data.alternateRoute || "No alternative suggested."}
            </div>
        </div>
    `;
    
    subscribeSection.classList.remove('hidden');
}

function hideDetailCard() {
    setSheetState('hidden');
    currentSelectedSpot = null;
    if (spotSelect) spotSelect.value = "";
    renderSpotList(allSpots);
    
    // Remove selection outline
    Object.values(markers).forEach(m => {
        const div = m.getElement();
        if(div && div.children[0]) div.children[0].classList.remove('selected');
    });
}

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

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Start application
init();
