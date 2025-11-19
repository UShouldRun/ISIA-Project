const CANVAS_SIZE_PX = 600;      // Fixed pixel size for the square canvas
const MAP_SIZE_CELLS = 1000;     // Total size of the simulated map (1000x1000)
const VIEWPORT_SIZE_CELLS = 100;   // The size of the received data chunk (100x100)
const CELL_SIZE_PX = CANVAS_SIZE_PX / VIEWPORT_SIZE_CELLS; // 600 / 100 = 6px

// --- State Variables (Global Scope) ---
let ws = null;
let isRunning = false;
let agents = [];
let resources = [];
let hazards = [];
let exploredCells = new Set();     
let selectedAgent = null;
let mapCells = {};           

// CRITICAL: World coordinates defining the loaded map chunk bounds
let mapMinX = 0;
let mapMinY = 0;
let mapMaxX = 0; // Calculated in initializeFullMap
let mapMaxY = 0; // Calculated in initializeFullMap

let viewportX = 0;           // Top-left x coordinate of the visible map section (World X)
let viewportY = 0;           // Top-left y coordinate of the visible map section (World Y)

// State variables for Mouse Panning
let isDragging = false;
let lastMouseX = 0;
let lastMouseY = 0;

const canvas = document.getElementById('mainCanvas');
const ctx = canvas.getContext('2d');
canvas.width = VIEWPORT_SIZE_CELLS * CELL_SIZE_PX;
canvas.height = VIEWPORT_SIZE_CELLS * CELL_SIZE_PX;

// Initialize
window.onload = function() {
  connectWebSocket();
  render();
  addMessage('System', 'Visualization interface loaded');
};

// WebSocket connection (omitted for brevity, assume original logic here)
function connectWebSocket() {
  const statusEl = document.getElementById('connection-status');
  
  try {
    // IMPORTANT: Ensure your Python server runs on this address
    ws = new WebSocket('ws://localhost:8080/ws'); 

    ws.onopen = () => {
      console.log('Connected to SPADE');
      statusEl.textContent = '✓ Connected';
      statusEl.className = 'connection-status status-connected';
      addMessage('System', 'Connected to SPADE system');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      // console.log(data);
      handleMessage(data);
    };

    ws.onerror = () => {
      console.log('WebSocket error');
      statusEl.textContent = '⚠ Connection Error';
      statusEl.className = 'connection-status status-simulation';
    };

    ws.onclose = () => {
      console.log('Disconnected from SPADE');
      statusEl.textContent = '✗ Disconnected';
      statusEl.className = 'connection-status status-disconnected';
      // Try to reconnect after 3 seconds
      setTimeout(connectWebSocket, 3000);
    };
  } catch (error) {
    console.log('WebSocket not available:', error);
    statusEl.textContent = '✗ No Connection';
    statusEl.className = 'connection-status status-disconnected';
  }
}
// --- Map Initialization and Update Functions ---

function initializeFullMap(cells) {
  mapCells = {}; // Clear any existing map data
  
  // CRITICAL: Reset bounds trackers
  mapMinX = MAP_SIZE_CELLS;
  mapMinY = MAP_SIZE_CELLS;
  mapMaxX = 0;
  mapMaxY = 0;
  
  // 1. Load data and determine minimum/maximum coordinates of the chunk
  cells.forEach(cell => {
    const key = `${cell.x},${cell.y}`;
    mapCells[key] = { ...cell };
    
    mapMinX = Math.min(mapMinX, cell.x);
    mapMinY = Math.min(mapMinY, cell.y);
    mapMaxX = Math.max(mapMaxX, cell.x);
    mapMaxY = Math.max(mapMaxY, cell.y);
  });
  
  addMessage('System', `Map data received (${cells.length} cells). Bounds: (${mapMinX}, ${mapMinY}) to (${mapMaxX}, ${mapMaxY})`);
  
  // 2. Adjust viewport to immediately show the received data chunk
  if (cells.length > 0) {
     // Set viewport origin to the smallest coordinates found in the data
     viewportX = mapMinX;
     viewportY = mapMinY;
     addMessage('System', `Viewport locked to chunk origin: (${viewportX}, ${viewportY})`);
  }
  
  render();
}

function updateMapCell(x, y, updates) {
  const key = `${x},${y}`;
  if (mapCells[key]) {
    mapCells[key] = { ...mapCells[key], ...updates };
    render();
  }
}

function handleMessage(data) {
  switch (data.type) {
    case 'full_map_init': 
      initializeFullMap(data.map_cells);
      break;
    case 'update_map': 
      initializeFullMap(data.map_cells);
      break;
    case 'map_cell_update': 
      updateMapCell(data.x, data.y, data.updates);
      break;
    case 'agent_update':
      updateAgent(data.agent);
      break;
    case 'resource_discovered':
      addResource(data.resource);
      break;
    case 'hazard_detected':
      addHazard(data.hazard);
      break;
    case 'cell_explored': 
      markCellExplored(data.x, data.y);
      break;
    case 'log_message':
      addMessage(data.sender, data.content);
      break;
    case 'stats':
      updateStats(data.stats);
      break;
  }
}

function updateAgent(agentData) {
  const index = agents.findIndex(a => a.id === agentData.id);
  if (index >= 0) {
    agents[index] = { ...agents[index], ...agentData };
  } else {
    agents.push(agentData);
  }
  renderAgents();
  render();
}

// DEPRECATED: Centering is disabled when the map size equals the viewport size
function centerViewportOnAgent(agent) {
   // If map bounds equal viewport size, centering is not useful and just shifts the map.
   // We keep the viewport locked to the map chunk's origin (mapMinX, mapMinY).
   // You can re-enable this if you load a map chunk LARGER than 100x100.
}

function addResource(resource) {
  const exists = resources.find(r => r.id === resource.id);
  if (!exists) {
    resources.push({ ...resource, discovered: true });
    addMessage('Discovery', `${resource.type} found at (${Math.floor(resource.x)}, ${Math.floor(resource.y)})`);
  }
  render();
}

function addHazard(hazard) {
  const exists = hazards.find(h => h.id === hazard.id);
  if (!exists) {
    hazards.push(hazard);
    addMessage('Alert', `Hazard: ${hazard.type} at (${Math.floor(hazard.x)}, ${Math.floor(hazard.y)})`);
  }
  render();
}

function markCellExplored(x, y) {
  exploredCells.add(`${x},${y}`);
  render();
}

function updateStats(stats) {
  document.getElementById('terrainMapped').textContent = stats.terrainMapped.toFixed(1) + '%';
  document.getElementById('resourcesFound').textContent = stats.resourcesFound;
  document.getElementById('avgEnergy').textContent = stats.totalEnergy.toFixed(0) + '%';
  document.getElementById('missionTime').textContent = stats.missionTime + 's';
}

function addMessage(sender, content) {
  const container = document.getElementById('messagesContainer');
  const time = new Date().toLocaleTimeString();
  const msg = document.createElement('div');
  msg.className = 'message';
  msg.innerHTML = `<span class="message-time">[${time}]</span> <span class="message-sender">${sender}:</span> ${content}`;
  
  // Append to the end (newest at bottom)
  container.appendChild(msg);
  
  // Auto-scroll to bottom to show newest message
  const messagesList = document.getElementById('messagesList');
  messagesList.scrollTop = messagesList.scrollHeight;
}

function renderAgents() {
  const list = document.getElementById('agentsList');
  list.innerHTML = '';
  
  if (agents.length === 0) {
    list.innerHTML = `<div style="color: #9ca3af; text-align: center; padding: 1rem;">Waiting for agents...</div>`;
    return;
  }
  
  agents.forEach(agent => {
    const item = document.createElement('div');
    item.className = 'agent-item' + (selectedAgent?.id === agent.id ? ' selected' : '');
    item.onclick = () => selectAgent(agent);
    
    const batteryClass = agent.battery > 50 ? 'battery-high' : 
              agent.battery > 20 ? 'battery-medium' : 'battery-low';

    // Check if agent is within the currently loaded map bounds (0 to 99)
    const isOnMap = agent.x >= mapMinX && agent.x <= mapMaxX &&
            agent.y >= mapMinY && agent.y <= mapMaxY;
    
    const agentStatusText = isOnMap ? agent.status : 
                `<span style="color: #fca5a5;">🚨 Out of Bounds</span>`;
    
    item.innerHTML = `
      <div class="agent-header">
        <div class="agent-name">${agent.id} (${Math.floor(agent.x)}, ${Math.floor(agent.y)})</div>
        <div class="agent-status">${agentStatusText}</div>
      </div>
      <div class="battery-bar">
        <div class="battery-fill ${batteryClass}" style="width: ${agent.battery}%"></div>
      </div>
    `;
    
    list.appendChild(item);
  });
}

function selectAgent(agent) {
  selectedAgent = agent;
  document.getElementById('commandsPanel').style.display = agent ? 'block' : 'none';
  
  // Add a console message if the agent is off-map to explain why the canvas doesn't move
  const isOnMap = agent.x >= mapMinX && agent.x <= mapMaxX &&
          agent.y >= mapMinY && agent.y <= mapMaxY;
  
  if (!isOnMap) {
    addMessage('System', `Agent ${agent.id} selected, but its position (${Math.floor(agent.x)}, ${Math.floor(agent.y)}) is outside the loaded map chunk (${mapMinX}-${mapMaxX}).`);
  }

  renderAgents();
  render();
}

function sendCommand(command) {
  if (ws && ws.readyState === WebSocket.OPEN && selectedAgent) {
    ws.send(JSON.stringify({
      type: 'command',
      command: command,
      agentId: selectedAgent.id
    }));
    addMessage('Command', `Sent: ${command} to ${selectedAgent.id}`);
  } else {
    addMessage('System', 'Not connected to SPADE - command ignored');
  }
}

function toggleSimulation() {
  isRunning = !isRunning;
  const btn = document.getElementById('startBtn');
  if (isRunning) {
    btn.textContent = 'Pause Mission';
    btn.className = 'btn-pause';
  } else {
    btn.textContent = 'Start Mission';
    btn.className = 'btn-start';
  }
}

function resetSimulation() {
  agents = [];
  resources = [];
  hazards = [];
  exploredCells = new Set();
  mapCells = {}; // Clear map data on reset
  selectedAgent = null;
  viewportX = 0; // Reset viewport to origin
  viewportY = 0;
  mapMinX = mapMinY = mapMaxX = mapMaxY = 0; // Reset bounds
  
  // Clear messages
  const container = document.getElementById('messagesContainer');
  container.innerHTML = '';
  
  renderAgents();
  render();
  addMessage('System', 'Visualization reset');
}

// --- Core Rendering Logic (Unchanged) ---

function render() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 1. Draw Terrain and Explored Cells (Background) - Optimized Loop
  for (let vx = 0; vx < VIEWPORT_SIZE_CELLS; vx++) {
    for (let vy = 0; vy < VIEWPORT_SIZE_CELLS; vy++) {
      // Calculate World Coordinates based on Viewport Origin
      const worldX = viewportX + vx;
      const worldY = viewportY + vy;
      const key = `${worldX},${worldY}`;
      const cell = mapCells[key]; 

      // Calculate drawing coordinates relative to the viewport
      const drawX = vx * CELL_SIZE_PX;
      const drawY = vy * CELL_SIZE_PX;
      
      if (cell) {
        // A. Draw Terrain Background based on the 'terrain' value
        let terrainColor = 'rgba(75, 85, 99, 0.3)'; 
        if (cell.terrain === 1) {
          terrainColor = 'rgba(209, 213, 219, 0.2)';
        } else if (cell.terrain === -1) {
          terrainColor = 'rgba(30, 41, 59, 0.6)';
        }

        if (cell.dust_storm === true) {
          console.log(cell.dust_storm)
          terrainColor = 'rgba(239, 181, 73, 0.7)';
        }

        ctx.fillStyle = terrainColor;
        ctx.fillRect(drawX, drawY, CELL_SIZE_PX, CELL_SIZE_PX);

        // B. Draw Explored Overlay
        if (exploredCells.has(key)) {
          ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
          ctx.fillRect(drawX, drawY, CELL_SIZE_PX, CELL_SIZE_PX);
        }

        // C. Draw Dust Storm Overlay (if active on this cell)
        if (cell.dust_storm) {
          ctx.fillStyle = 'rgba(245, 158, 11, 0.4)';
          ctx.fillRect(drawX, drawY, CELL_SIZE_PX, CELL_SIZE_PX);
        }
      } else {
        // Draw empty background if no cell data is loaded yet (off-map)
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(drawX, drawY, CELL_SIZE_PX, CELL_SIZE_PX);
      }
    }
  }


  // 2. Draw Grid (Only for the viewport)
  ctx.strokeStyle = '#374151';
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= VIEWPORT_SIZE_CELLS; i++) {
    // Vertical lines
    ctx.beginPath();
    ctx.moveTo(i * CELL_SIZE_PX, 0);
    ctx.lineTo(i * CELL_SIZE_PX, VIEWPORT_SIZE_CELLS * CELL_SIZE_PX);
    ctx.stroke();
    // Horizontal lines
    ctx.beginPath();
    ctx.moveTo(0, i * CELL_SIZE_PX);
    ctx.lineTo(VIEWPORT_SIZE_CELLS * CELL_SIZE_PX, i * CELL_SIZE_PX);
    ctx.stroke();
  }

  // 3. Draw Hazards, Resources, and Agents (Foreground items)
  [...hazards, ...resources, ...agents].forEach(item => {
    // Only draw if the item is within the viewport
    if (item.x >= viewportX && item.x < viewportX + VIEWPORT_SIZE_CELLS &&
      item.y >= viewportY && item.y < viewportY + VIEWPORT_SIZE_CELLS) {

      // Calculate drawing coordinates relative to the viewport
      const drawX = (item.x - viewportX) * CELL_SIZE_PX + CELL_SIZE_PX / 2;
      const drawY = (item.y - viewportY) * CELL_SIZE_PX + CELL_SIZE_PX / 2;

      if (item.type === 'storm' || item.type === 'rock') {
        // Hazards
        ctx.fillStyle = item.type === 'storm' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(245, 158, 11, 0.3)';
        ctx.beginPath();
        const radiusPx = (item.radius || 1) * CELL_SIZE_PX;
        ctx.arc(drawX, drawY, radiusPx, 0, 2 * Math.PI);
        ctx.fill();

      } else if (item.discovered !== undefined) {
        // Resources
        ctx.fillStyle = item.discovered ? 'rgba(59, 130, 246, 0.9)' : 'rgba(16, 185, 129, 0.3)';
        ctx.beginPath();
        ctx.arc(drawX, drawY, CELL_SIZE_PX * 0.4, 0, 2 * Math.PI); 
        ctx.fill();
        
        if (item.discovered) {
          ctx.strokeStyle = '#10b981';
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      } else {
        // Agents
        const agent = item;
        ctx.fillStyle = agent.color || '#ffffff';
        ctx.beginPath();
        
        const shapeSize = CELL_SIZE_PX; 

        if (agent.type === 'rover') {
          ctx.rect(drawX - shapeSize/2, drawY - shapeSize/2, shapeSize, shapeSize);
          ctx.fill();
        } else if (agent.type === 'drone') {
          ctx.moveTo(drawX, drawY - shapeSize/2);
          ctx.lineTo(drawX + shapeSize/2, drawY + shapeSize/2);
          ctx.lineTo(drawX - shapeSize/2, drawY + shapeSize/2);
          ctx.closePath();
          ctx.fill();
        } else if (agent.type === 'base') {
          // Draw radius circle (outline only)
          ctx.strokeStyle = agent.color || '#8b5cf6';
          ctx.lineWidth = 2;
          ctx.arc(drawX, drawY, (agent.radius || 5) * CELL_SIZE_PX, 0, 2 * Math.PI);
          ctx.stroke();
          
          // Draw center point (filled)
          ctx.fillStyle = agent.color || '#8b5cf6';
          ctx.beginPath();
          ctx.arc(drawX, drawY, CELL_SIZE_PX * 0.3, 0, 2 * Math.PI);
          ctx.fill();
        }
        
        // Selection highlight
        if (selectedAgent?.id === agent.id) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(drawX, drawY, CELL_SIZE_PX * 0.8, 0, 2 * Math.PI);
          ctx.stroke();
        }
      }
    }
  });
}


// --- Interaction Handlers (Click and Pan) ---
function clampViewport(x, y) {
  // Calculate the maximum possible START coordinate (map Max - viewport Size + 1)
  const maxViewX = mapMaxX - VIEWPORT_SIZE_CELLS + 1;
  const maxViewY = mapMaxY - VIEWPORT_SIZE_CELLS + 1;

  // Clamp the new viewport start coordinates
  let newX = Math.max(mapMinX, Math.min(x, maxViewX));
  let newY = Math.max(mapMinY, Math.min(y, maxViewY));
  
  // Handle edge case where map data hasn't been loaded yet (mapMinX/Y is huge/tiny)
  if (mapMaxX === 0 && mapMinX === MAP_SIZE_CELLS) {
    newX = 0;
    newY = 0;
  }

  viewportX = newX;
  viewportY = newY;
}

// Mouse Down (Start Dragging)
canvas.addEventListener('mousedown', function(e) {
  isDragging = true;
  lastMouseX = e.clientX;
  lastMouseY = e.clientY;
  canvas.classList.add('grabbing');
  e.preventDefault(); 
});

// Mouse Up (Stop Dragging)
document.addEventListener('mouseup', function() {
  isDragging = false;
  canvas.classList.remove('grabbing');
});

// Mouse Move (Dragging Logic)
canvas.addEventListener('mousemove', function(e) {
  if (!isDragging || mapMaxX === 0) return; // Don't pan if no data is loaded

  const deltaX = e.clientX - lastMouseX;
  const deltaY = e.clientY - lastMouseY;

  // Convert pixel change to cell change 
  const cellStepX = Math.floor(deltaX / CELL_SIZE_PX);
  const cellStepY = Math.floor(deltaY / CELL_SIZE_PX);
  
  // Calculate potential new viewport positions
  let potentialX = viewportX - cellStepX;
  let potentialY = viewportY - cellStepY;
  
  // Clamp the viewport to the known map bounds
  clampViewport(potentialX, potentialY);
  
  lastMouseX = e.clientX;
  lastMouseY = e.clientY;

  render();
});

// Canvas click handler (for agent selection, runs after mouseup)
canvas.addEventListener('click', function(e) {
  const rect = canvas.getBoundingClientRect();
  // Convert click coordinates to viewport cells, then to world cells
  const viewportCellX = Math.floor((e.clientX - rect.left) / CELL_SIZE_PX);
  const viewportCellY = Math.floor((e.clientY - rect.top) / CELL_SIZE_PX);

  const worldX = viewportX + viewportCellX;
  const worldY = viewportY + viewportCellY;

  // Find clicked agent in world coordinates
  const clicked = agents.find(agent => {
    return Math.floor(agent.x) === worldX && Math.floor(agent.y) === worldY;
  });

  if (clicked) {
    selectAgent(clicked);
  }
});

// Simple panning using arrow keys (kept as an alternative)
document.addEventListener('keydown', (e) => {
  if (mapMaxX === 0) return; // Don't pan if no data is loaded
  const step = 1; 
  let changed = false;
  let potentialX = viewportX;
  let potentialY = viewportY;

  if (e.key === 'ArrowRight') {
    potentialX += step;
    changed = true;
  } else if (e.key === 'ArrowLeft') {
    potentialX -= step;
    changed = true;
  } else if (e.key === 'ArrowDown') {
    potentialY += step;
    changed = true;
  } else if (e.key === 'ArrowUp') {
    potentialY -= step;
    changed = true;
  }
  
  if (changed) {
    e.preventDefault();
    clampViewport(potentialX, potentialY);
    render();
  }
});

setInterval(render, 100);
