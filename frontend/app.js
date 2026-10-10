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

// Reports Layer
const reportsLayer = L.layerGroup().addTo(map);
let allReports = [];
let reportsPollingInterval = null;

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

const demoBanner = document.getElementById('demo-banner');

// Custom Icons with 44px hit area
const createIcon = (level) => {
    const levelClass = level.toLowerCase();
    const markerHtml = `<div class="marker-hit-area"><div class="marker-pin ${levelClass}"></div></div>`;
    return L.divIcon({ html: markerHtml, className: 'custom-div-icon', iconSize: [44, 44], iconAnchor: [22, 22] });
};

// Event Listeners
simulateToggle.addEventListener('change', (e) => {
    isSimulating = e.target.checked;
    if (demoBanner) {
        if (isSimulating) {
            demoBanner.classList.remove('hidden');
        } else {
            demoBanner.classList.add('hidden');
        }
    }
    fetchRisks();
});

const reportsToggle = document.getElementById('reports-toggle');
if (reportsToggle) {
    reportsToggle.addEventListener('change', (e) => {
        if (e.target.checked) {
            map.addLayer(reportsLayer);
        } else {
            map.removeLayer(reportsLayer);
        }
    });
}

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

        // Fit bounds with padding so view is not zoomed out to Thane and Navi Mumbai
        if (allSpots.length > 0) {
            const bounds = L.latLngBounds(allSpots.map(s => [s.lat, s.lng]));
            map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
        }

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
        markers[currentSelectedSpot].setZIndexOffset(0);
        const div = markers[currentSelectedSpot].getElement();
        if (div) {
            const pin = div.querySelector('.marker-pin');
            if (pin) pin.classList.remove('selected');
        }
    }
    
    currentSelectedSpot = spotId;
    if (spotSelect) spotSelect.value = spotId;
    
    const spot = allSpots.find(s => s.spotId === spotId);
    if (spot) {
        // Fly to spot and offset marker south on mobile so it stays visible above the sheet
        if (window.innerWidth < 900) {
            map.flyTo([spot.lat - 0.022, spot.lng], 13, { duration: 0.8 });
        } else {
            map.flyTo([spot.lat, spot.lng], 14, { duration: 0.8 });
        }
    }
    
    if (markers[spotId]) {
        markers[spotId].setZIndexOffset(1000); // Bring selected marker to front
        const div = markers[spotId].getElement();
        if (div) {
            const pin = div.querySelector('.marker-pin');
            if (pin) pin.classList.add('selected');
        }
    }
    
    renderSpotList(allSpots);
    renderDetailCard(spotId);
    fetchReportsForSpot(spotId);
    
    if (window.innerWidth < 900) {
        setSheetState('half'); // Open at half state (about 50vh), not full
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
        document.getElementById('report-action-area').classList.add('hidden');
        document.getElementById('community-reports-section').classList.add('hidden');
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
    
    const isBedrock = data.alertSource === 'bedrock';
    const aiBadgeHtml = isBedrock ? '<span class="ai-generated-badge">✨ AI-generated</span>' : '';
    
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
                <span class="tide-title">High Tide & Rainfall Timeline</span>
                ${data.tide.coincidesWithRain ? '<div class="tide-overlap-chip">⚠️ Rain + high tide overlap</div>' : ''}
            </div>
            <div class="tide-info">
                Next peak at <strong>${data.tide.nextHighTideTime}</strong> (${data.tide.nextHighTideHeight}m) <span class="tide-approx-note">(approx. model value)</span>
            </div>
            <div class="tide-legend">
                <span class="tide-legend-item"><span class="tide-legend-bar"></span> Rain (mm/h)</span>
                <span class="tide-legend-item"><span class="tide-legend-line"></span> Tide height</span>
            </div>
            <div class="mini-timeline-container">
                <svg viewBox="0 0 300 95" width="100%" height="100%" style="overflow: visible;" aria-label="Tide and Rain timeline">
                    <title>24-hour Rain Forecast and Tide Timeline</title>
                    <desc>Timeline showing forecasted rainfall in mm per hour and tidal height fluctuation over 24 hours.</desc>
                    
                    <!-- Baseline Axis -->
                    <line x1="20" y1="70" x2="280" y2="70" stroke="var(--border)" stroke-width="1" />
                    
                    <!-- Highlighted Overlap Zone -->
                    ${data.tide.coincidesWithRain ? `
                        <rect x="25" y="8" width="55" height="62" fill="var(--high-bg)" opacity="0.65" rx="4" />
                        <text x="52" y="19" text-anchor="middle" font-size="9" font-weight="700" fill="var(--high-color)">Overlap</text>
                    ` : ''}
                    
                    <!-- Rain Forecast Bars (mm/h) -->
                    <rect x="30" y="${data.tide.coincidesWithRain ? '28' : '48'}" width="14" height="${data.tide.coincidesWithRain ? '42' : '22'}" fill="var(--accent)" opacity="0.8" rx="2" />
                    <rect x="52" y="${data.tide.coincidesWithRain ? '22' : '52'}" width="14" height="${data.tide.coincidesWithRain ? '48' : '18'}" fill="var(--accent)" opacity="0.9" rx="2" />
                    <rect x="85" y="52" width="14" height="18" fill="var(--accent)" opacity="0.45" rx="2" />
                    <rect x="145" y="56" width="14" height="14" fill="var(--accent)" opacity="0.3" rx="2" />
                    <rect x="205" y="60" width="14" height="10" fill="var(--accent)" opacity="0.25" rx="2" />
                    <rect x="260" y="62" width="14" height="8" fill="var(--accent)" opacity="0.2" rx="2" />
                    
                    <!-- Tide Curve Path -->
                    <path d="M 20 62 Q 55 18 110 50 T 200 48 T 280 62" fill="none" stroke="var(--text-main)" stroke-width="2.5" stroke-linecap="round" />
                    
                    <!-- Peak Dot and Time Label -->
                    <circle cx="55" cy="24" r="4.5" fill="var(--high-color)" stroke="#ffffff" stroke-width="2" />
                    <text x="55" y="14" text-anchor="middle" font-size="9.5" font-weight="700" fill="var(--text-main)">${data.tide.nextHighTideTime}</text>
                    
                    <!-- Time Axis Ticks and Labels in IST -->
                    <text x="20" y="85" text-anchor="middle" font-size="9.5" font-weight="500" fill="var(--text-muted)">Now</text>
                    <text x="85" y="85" text-anchor="middle" font-size="9.5" font-weight="500" fill="var(--text-muted)">+6h</text>
                    <text x="150" y="85" text-anchor="middle" font-size="9.5" font-weight="500" fill="var(--text-muted)">+12h</text>
                    <text x="215" y="85" text-anchor="middle" font-size="9.5" font-weight="500" fill="var(--text-muted)">+18h</text>
                    <text x="280" y="85" text-anchor="middle" font-size="9.5" font-weight="500" fill="var(--text-muted)">+24h</text>
                    <text x="150" y="94" text-anchor="middle" font-size="8" font-weight="400" fill="var(--text-muted)">Timeline in IST</text>
                </svg>
            </div>
        </div>
        ` : ''}

        <div class="ai-alert">
            <div class="ai-alert-header">
                <div class="lang-toggle">
                    <button class="lang-btn active" onclick="setLanguage('en')" aria-label="English">EN</button>
                    <button class="lang-btn" onclick="setLanguage('hi')" aria-label="Hindi">हिंदी</button>
                    <button class="lang-btn" onclick="setLanguage('mr')" aria-label="Marathi">मराठी</button>
                </div>
                ${aiBadgeHtml}
            </div>
            <p id="alert-text-container" class="alert-text" aria-live="polite" data-en="${alert.en}" data-hi="${alert.hi}" data-mr="${alert.mr}">${alert.en}</p>
        </div>
        
        <div class="alternate-route">
            <svg class="route-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polygon points="3 11 22 2 13 21 11 13 3 11"/>
            </svg>
            <div>
                <strong style="display:block;font-size:12px;color:var(--text-muted);margin-bottom:2px">Safer Route</strong>
                ${data.alternateRoute || "No alternative suggested."}
            </div>
        </div>
    `;
    
    // Always show community reports section in the card
    const reportsSection = document.getElementById('community-reports-section');
    const reportsActionArea = document.getElementById('report-action-area');
    
    reportsSection.classList.remove('hidden');
    const rCount = (data.reports && data.reports.countLast2h) ? data.reports.countLast2h : 0;
    const isConfirmed = data.reports && data.reports.communityConfirmed;
    
    if (rCount > 0) {
        reportsSection.innerHTML = `
            <div class="reports-header">
                <span class="reports-title">Community Reports (${rCount})</span>
                ${isConfirmed ? '<span class="community-chip">Community confirmed</span>' : ''}
            </div>
            <div class="report-list" id="report-list-container">
                <div class="skeleton" style="height: 44px; border-radius: 8px;"></div>
            </div>
        `;
    } else {
        reportsSection.innerHTML = `
            <div class="reports-header">
                <span class="reports-title">Community Reports</span>
            </div>
            <div class="reports-empty">
                <p>No reports in the last 2 hours. Be the first to report.</p>
            </div>
            <div class="report-list" id="report-list-container" style="display:none;"></div>
        `;
    }
    
    reportsActionArea.classList.remove('hidden');
    subscribeSection.classList.remove('hidden');
}

function hideDetailCard() {
    setSheetState('hidden');
    if (currentSelectedSpot && markers[currentSelectedSpot]) {
        markers[currentSelectedSpot].setZIndexOffset(0);
    }
    currentSelectedSpot = null;
    if (spotSelect) spotSelect.value = "";
    renderSpotList(allSpots);
    
    // Remove selection outline
    Object.values(markers).forEach(m => {
        m.setZIndexOffset(0);
        const div = m.getElement();
        if (div) {
            const pin = div.querySelector('.marker-pin');
            if (pin) pin.classList.remove('selected');
        }
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

// ----------------------------------------------------
// REPORTS LOGIC
// ----------------------------------------------------
const reportModal = document.getElementById('report-modal');
const openReportBtn = document.getElementById('open-report-modal');
const closeReportBtn = document.getElementById('close-report-modal');
const reportNote = document.getElementById('report-note');
const noteCount = document.getElementById('note-count');
const reportPhoto = document.getElementById('report-photo');
const triggerPhotoBtn = document.getElementById('trigger-photo-upload');
const photoPreviewContainer = document.getElementById('photo-preview-container');
const photoPreview = document.getElementById('photo-preview');
const removePhotoBtn = document.getElementById('remove-photo');
const reportForm = document.getElementById('report-form');
let resizedPhotoBlob = null;

if (openReportBtn) openReportBtn.addEventListener('click', () => {
    reportModal.classList.remove('hidden');
    // Basic focus trap or just focus first input
    const firstInput = reportForm.querySelector('input[name="severity"]');
    if (firstInput) firstInput.focus();
});

if (closeReportBtn) closeReportBtn.addEventListener('click', () => {
    reportModal.classList.add('hidden');
    reportForm.reset();
    clearPhoto();
});

reportNote.addEventListener('input', () => {
    noteCount.textContent = reportNote.value.length;
});

triggerPhotoBtn.addEventListener('click', () => reportPhoto.click());

reportPhoto.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    try {
        triggerPhotoBtn.textContent = 'Processing...';
        resizedPhotoBlob = await resizeImage(file, 1280, 0.8);
        const url = URL.createObjectURL(resizedPhotoBlob);
        photoPreview.src = url;
        triggerPhotoBtn.classList.add('hidden');
        photoPreviewContainer.classList.remove('hidden');
    } catch (err) {
        showToast('Error processing image.', 'error');
    } finally {
        triggerPhotoBtn.textContent = '📷 Add Photo';
    }
});

removePhotoBtn.addEventListener('click', clearPhoto);

function clearPhoto() {
    reportPhoto.value = '';
    resizedPhotoBlob = null;
    photoPreview.src = '';
    photoPreviewContainer.classList.add('hidden');
    triggerPhotoBtn.classList.remove('hidden');
}

function resizeImage(file, maxSide, quality) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
            let w = img.width;
            let h = img.height;
            if (w > h) {
                if (w > maxSide) { h = Math.round(h * maxSide / w); w = maxSide; }
            } else {
                if (h > maxSide) { w = Math.round(w * maxSide / h); h = maxSide; }
            }
            const canvas = document.createElement('canvas');
            canvas.width = w; canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, w, h);
            canvas.toBlob((blob) => {
                if (blob) resolve(blob);
                else reject(new Error('Canvas toBlob failed'));
            }, 'image/jpeg', quality);
        };
        img.onerror = reject;
        const reader = new FileReader();
        reader.onload = (e) => { img.src = e.target.result; };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

reportForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('submit-report-btn');
    const severity = reportForm.querySelector('input[name="severity"]:checked')?.value;
    const note = reportNote.value.trim();
    const spotId = currentSelectedSpot;
    
    if (!spotId) return;
    
    btn.disabled = true;
    btn.textContent = 'Submitting...';
    
    try {
        let photoKey = null;
        
        if (resizedPhotoBlob) {
            btn.textContent = 'Uploading photo...';
            const uploadRes = await fetch(`${API_BASE_URL}/reports/upload-url`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ contentType: 'image/jpeg' })
            });
            if (!uploadRes.ok) throw new Error('Failed to get upload URL');
            const uploadData = await uploadRes.json();
            photoKey = uploadData.photoKey;
            
            const putRes = await fetch(uploadData.uploadUrl, {
                method: 'PUT',
                headers: { 'Content-Type': 'image/jpeg' },
                body: resizedPhotoBlob
            });
            if (!putRes.ok) throw new Error('Failed to upload photo');
        }
        
        btn.textContent = 'Saving report...';
        const reportRes = await fetch(`${API_BASE_URL}/reports`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ spotId, severity, note, photoKey })
        });
        
        const reportData = await reportRes.json();
        if (!reportRes.ok) {
            if (reportRes.status === 429) throw new Error(reportData.error || 'Rate limited');
            throw new Error('Failed to submit report');
        }
        
        showToast('Thanks, your report helps others nearby!', 'success');
        reportModal.classList.add('hidden');
        reportForm.reset();
        clearPhoto();
        
        // Refresh risks and reports
        await fetchRisks();
        if (currentSelectedSpot === spotId) {
            fetchReportsForSpot(spotId);
        }
        
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Submit Report';
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !reportModal.classList.contains('hidden')) {
        closeReportBtn.click();
    }
});

async function fetchReportsForSpot(spotId) {
    if (!spotId) return;
    try {
        const res = await fetch(`${API_BASE_URL}/reports?spotId=${spotId}`);
        if (!res.ok) return;
        const reports = await res.json();
        
        // Render in the list
        const container = document.getElementById('report-list-container');
        if (container) {
            container.innerHTML = '';
            if (reports && reports.length > 0) {
                container.style.display = 'flex';
                reports.slice(0, 3).forEach(r => {
                    let timeStr = "recently";
                    const ageSecs = Math.floor(Date.now()/1000) - r.createdAt;
                    if (ageSecs < 60) timeStr = "just now";
                    else if (ageSecs < 3600) timeStr = `${Math.floor(ageSecs/60)} min ago`;
                    else timeStr = `${Math.floor(ageSecs/3600)} hr ago`;
                    
                    const sevMap = {
                        'ANKLE': '<span class="sev-tag ankle">Ankle deep</span>',
                        'KNEE': '<span class="sev-tag knee">Knee deep</span>',
                        'WAIST': '<span class="sev-tag waist">Waist deep</span>',
                        'IMPASSABLE': '<span class="sev-tag impassable">Can\'t pass</span>'
                    };
                    
                    const row = document.createElement('div');
                    row.className = 'report-row';
                    let imgHtml = '';
                    if (r.photoUrl) {
                        imgHtml = `<img src="${r.photoUrl}" class="report-thumb" alt="Flood photo" loading="lazy">`;
                    }
                    
                    const noteDiv = document.createElement('div');
                    noteDiv.className = 'report-note';
                    noteDiv.textContent = r.note;
                    
                    row.innerHTML = `
                        ${imgHtml}
                        <div style="flex-grow:1">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span class="report-sev">${sevMap[r.severity] || r.severity}</span>
                                <span class="report-time">${timeStr}</span>
                            </div>
                            ${r.note ? noteDiv.outerHTML : ''}
                        </div>
                    `;
                    container.appendChild(row);
                });
            } else {
                container.style.display = 'block';
                container.innerHTML = '<div class="reports-empty"><p>No reports in the last 2 hours. Be the first to report.</p></div>';
            }
        }
        
        // Render on map
        reportsLayer.clearLayers();
        const spot = allSpots.find(s => s.spotId === spotId);
        if (spot) {
            reports.forEach((r, idx) => {
                // jitter
                const jitterLat = spot.lat + (Math.random() - 0.5) * 0.002;
                const jitterLng = spot.lng + (Math.random() - 0.5) * 0.002;
                const icon = L.divIcon({ html: '<div class="report-pin"></div>', className: 'custom-div-icon', iconSize: [18, 18], iconAnchor: [9, 18] });
                
                const sevMap = { 'ANKLE': '👟 Ankle', 'KNEE': '👢 Knee', 'WAIST': '🩳 Waist', 'IMPASSABLE': '🛑 Impassable' };
                let popupHtml = `<strong>${sevMap[r.severity] || r.severity}</strong><br>`;
                if (r.note) popupHtml += `<div>${r.note.replace(/</g, "&lt;")}</div>`; // escape basic tags
                if (r.photoUrl) popupHtml += `<img src="${r.photoUrl}" style="width:100px; border-radius:4px; margin-top:4px;">`;
                
                L.marker([jitterLat, jitterLng], { icon }).addTo(reportsLayer).bindPopup(popupHtml);
            });
        }
        
    } catch (e) {
        console.error("Failed to fetch reports for spot", e);
    }
}

// Polling
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        startPolling();
    } else {
        stopPolling();
    }
});

function startPolling() {
    if (!reportsPollingInterval) {
        reportsPollingInterval = setInterval(() => {
            if (currentSelectedSpot) {
                // re-fetch risk to update score and reports list seamlessly
                fetchRiskForSingleSpot(currentSelectedSpot);
                fetchReportsForSpot(currentSelectedSpot);
            }
        }, 60000);
    }
}

function stopPolling() {
    if (reportsPollingInterval) {
        clearInterval(reportsPollingInterval);
        reportsPollingInterval = null;
    }
}

async function fetchRiskForSingleSpot(spotId) {
    try {
        const simParam = isSimulating ? '&simulate=heavy' : '';
        const res = await fetch(`${API_BASE_URL}/risk?spotId=${spotId}${simParam}`);
        if (res.ok) {
            const data = await res.json();
            currentRiskData[spotId] = data;
            if (markers[spotId]) {
                markers[spotId].setIcon(createIcon(data.riskLevel));
            }
            if (currentSelectedSpot === spotId) {
                renderDetailCard(spotId);
            }
        }
    } catch(e) {}
}

startPolling();
