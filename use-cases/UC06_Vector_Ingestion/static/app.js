// static/app.js
class VectorDashboard {
    constructor() {
        this.apiBase = window.location.origin;
        this.currentFile = null;
        this.charts = {};
        this.uploadQueue = [];
        this.activityLog = [];
        this.systemStats = {};
        this.init();
    }

    async init() {
        this.updateTime();
        this.setupEventListeners();
        this.setupCharts();
        this.loadSystemStats();
        this.refreshDashboard();
        this.loadSources();

        // Auto-refresh ogni 10 secondi
        setInterval(() => this.refreshDashboard(), 10000);
        setInterval(() => this.updateTime(), 1000);

        this.logActivity('Sistema inizializzato', 'info');
    }

    updateTime() {
        const now = new Date();
        document.getElementById('current-time').textContent = 
            now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    }

    async refreshDashboard() {
        try {
            await Promise.all([
                this.loadSystemStats(),
                this.updateDLQStats(),
                this.updateActivityLog()
            ]);
        } catch (error) {
            console.error('Dashboard refresh failed:', error);
        }
    }

    async loadSystemStats() {
        try {
            const response = await this.apiCall('/stats');
            this.systemStats = response;
            
            // Update UI
            this.updateStatsUI(response);
            
            if (response.embedder) {
                document.getElementById('embedder-model').textContent = 
                    response.embedder.model_name || 'Unknown';
                document.getElementById('cache-hit-rate').textContent = 
                    (response.embedder.cache_hit_rate * 100 || 0).toFixed(1) + '%';
                document.getElementById('device-info').textContent = 
                    response.embedder.device || 'CPU';
            }
            
            if (response.system) {
                document.getElementById('uptime').textContent = 
                    this.formatUptime(response.system.uptime_seconds);
                document.getElementById('memory-usage').textContent = 
                    response.system.memory_usage_mb || 'N/A';
            }
            
            return response;
        } catch (error) {
            console.error('Failed to load system stats:', error);
            return null;
        }
    }

    updateStatsUI(stats) {
        // Documenti totali
        const totalDocs = stats.system?.total_processed_files || 0;
        document.getElementById('total-docs').textContent = totalDocs;
        document.getElementById('docs-progress').style.width = 
            Math.min(totalDocs, 100) + '%';
        
        // Chunks
        const totalChunks = stats.vector_store?.total_chunks || 0;
        document.getElementById('total-chunks').textContent = 
            totalChunks.toLocaleString();
        document.getElementById('chunks-progress').style.width = 
            Math.min(totalChunks / 1000 * 100, 100) + '%';
        
        // Throughput
        const throughput = stats.embedder?.throughput_docs_per_sec || 0;
        document.getElementById('throughput').textContent = 
            Math.round(throughput).toLocaleString();
        
        // Fallimenti
        const failedCount = stats.system?.failed_operations || 0;
        document.getElementById('failed-count').textContent = failedCount;
        
        const totalOps = totalChunks + (stats.system?.total_processed_files || 0);
        const failureRate = totalOps > 0 ? (failedCount / totalOps * 100).toFixed(1) : 0;
        document.getElementById('failure-rate').textContent = 
            `${failureRate}% failure rate`;
        
        // Update DLQ chart
        this.updateDLQChart(stats.dlq);
    }

    async updateDLQStats() {
        try {
            const response = await this.apiCall('/dlq/stats');
            
            const failedChunks = response.failed_chunks?.total || 0;
            const failedFiles = response.failed_files?.total || 0;
            const totalFailed = failedChunks + failedFiles;
            
            document.getElementById('dlq-count').textContent = totalFailed;
            
            // Update DLQ alert
            const dlqAlert = document.getElementById('dlq-alert');
            if (totalFailed > 0) {
                dlqAlert.className = 'alert alert-warning alert-custom';
                dlqAlert.querySelector('.alert-heading').textContent = totalFailed;
                dlqAlert.querySelector('p').textContent = 'failed operations pending';
            } else {
                dlqAlert.className = 'alert alert-success alert-custom';
                dlqAlert.querySelector('.alert-heading').textContent = '0';
                dlqAlert.querySelector('p').textContent = 'No failed operations';
            }
            
            return response;
        } catch (error) {
            console.error('Failed to load DLQ stats:', error);
            return null;
        }
    }

    setupEventListeners() {
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('file-input');

        // Click to browse
        dropzone.addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON' && e.target.id !== 'file-input') {
                fileInput.click();
            }
        });

        // Drag and drop
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                this.handleFiles(e.dataTransfer.files);
            }
        });

        // File input change — support multi-select
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFiles(e.target.files);
            }
        });

        // Batch mode toggle: enable multiple file selection
        document.getElementById('mode-batch').addEventListener('change', () => {
            fileInput.setAttribute('multiple', 'true');
        });
        document.getElementById('mode-single').addEventListener('change', () => {
            fileInput.removeAttribute('multiple');
        });

        // Search on Enter
        document.getElementById('search-query').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.performSearch();
            }
        });

        // Live search with 400ms debounce
        let searchDebounce = null;
        document.getElementById('search-query').addEventListener('input', (e) => {
            clearTimeout(searchDebounce);
            const val = e.target.value.trim();
            if (val.length >= 3) {
                searchDebounce = setTimeout(() => this.performSearch(), 400);
            }
        });
    }

    handleFiles(files) {
        if (files.length > 1) {
            // Multiple files → batch endpoint
            this.uploadBatch(files);
        } else if (files.length === 1) {
            this.addToUploadQueue(files[0]);
            this.processUploadQueue();
        }
    }

    async uploadBatch(files) {
        const batchDiv = document.getElementById('batch-results');
        const fileList = Array.from(files);

        batchDiv.innerHTML = `
            <div class="alert alert-info py-2 small">
                <div class="spinner-border spinner-border-sm me-2"></div>
                Upload batch di ${fileList.length} file in corso...
            </div>
        `;

        const formData = new FormData();
        for (const f of fileList) {
            formData.append('files', f);
        }
        formData.append('chunk_size', document.getElementById('chunk-size').value);
        formData.append('chunk_overlap', document.getElementById('chunk-overlap').value);

        try {
            const result = await this.apiCall('/upload/batch', { method: 'POST', body: formData });

            let html = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="fw-semibold small">Batch completato</span>
                    <span class="badge bg-secondary">${result.total_chunks} chunks totali</span>
                </div>
            `;

            result.results.forEach(r => {
                const ok = r.status === 'success';
                html += `
                    <div class="batch-result-item d-flex justify-content-between align-items-center
                                py-1 border-bottom">
                        <span class="${ok ? '' : 'text-danger'}">
                            <i class="bi bi-${ok ? 'check-circle text-success' : 'x-circle text-danger'} me-1"></i>
                            ${r.filename}
                        </span>
                        <span class="text-muted">
                            ${ok ? r.chunks_processed + ' chunks' : r.error || 'errore'}
                            &nbsp;·&nbsp;${r.processing_time_ms.toFixed(0)}ms
                        </span>
                    </div>
                `;
            });

            const badgeClass = result.failed > 0 ? 'warning' : 'success';
            html = `
                <div class="card border-${badgeClass}">
                    <div class="card-header py-1 small fw-semibold bg-${badgeClass} bg-opacity-10">
                        ${result.successful}/${result.total_files} OK
                        &nbsp;·&nbsp;${result.total_chunks} chunks
                        &nbsp;·&nbsp;${result.processing_time_ms.toFixed(0)}ms
                    </div>
                    <div class="card-body py-2">${html}</div>
                </div>
            `;
            batchDiv.innerHTML = html;

            this.logActivity(
                `Batch: ${result.successful}/${result.total_files} file ok, ${result.total_chunks} chunks`,
                result.failed > 0 ? 'warning' : 'success'
            );
            this.refreshDashboard();

        } catch (error) {
            batchDiv.innerHTML = `
                <div class="alert alert-danger small py-2">
                    <i class="bi bi-exclamation-triangle me-1"></i>
                    Batch fallito: ${error.message}
                </div>
            `;
            this.logActivity('Batch upload fallito: ' + error.message, 'error');
        }
    }

    addToUploadQueue(file) {
        const fileId = 'file_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        
        this.uploadQueue.push({
            id: fileId,
            file: file,
            status: 'pending',
            progress: 0
        });
        
        this.updateUploadQueueUI();
    }

    updateUploadQueueUI() {
        const queueDiv = document.getElementById('upload-queue');
        
        if (this.uploadQueue.length === 0) {
            queueDiv.innerHTML = '';
            return;
        }
        
        let html = '<h6 class="mb-3">Upload Queue</h6>';
        
        this.uploadQueue.forEach(item => {
            const statusColor = {
                'pending': 'secondary',
                'uploading': 'primary',
                'processing': 'warning',
                'completed': 'success',
                'failed': 'danger'
            }[item.status] || 'secondary';
            
            html += `
                <div class="card result-card mb-2">
                    <div class="card-body py-2">
                        <div class="d-flex align-items-center">
                            <div class="flex-grow-1">
                                <div class="d-flex justify-content-between">
                                    <span class="fw-bold">${item.file.name}</span>
                                    <span class="badge bg-${statusColor}">${item.status}</span>
                                </div>
                                <div class="progress progress-custom mt-1">
                                    <div class="progress-bar" style="width: ${item.progress}%"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        queueDiv.innerHTML = html;
    }

    async processUploadQueue() {
        while (this.uploadQueue.length > 0) {
            const item = this.uploadQueue[0];
            item.status = 'uploading';
            this.updateUploadQueueUI();
            
            await this.uploadFile(item);
            
            // Remove from queue
            this.uploadQueue.shift();
            this.updateUploadQueueUI();
        }
    }

    // Helper: legge un File come testo (Promise)
    readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = () => reject(new Error('Impossibile leggere il file'));
            reader.readAsText(file, 'utf-8');
        });
    }

    async uploadFile(queueItem) {
        try {
            queueItem.status = 'processing';
            queueItem.progress = 30;
            this.updateUploadQueueUI();

            const chunkSize = document.getElementById('chunk-size').value;
            const chunkOverlap = document.getElementById('chunk-overlap').value;
            const filename = queueItem.file.name.toLowerCase();
            const formData = new FormData();

            // Determine endpoint and populate FormData accordingly
            let endpoint;
            if (filename.endsWith('.pdf')) {
                endpoint = '/upload/pdf';
                formData.append('file', queueItem.file);
                formData.append('chunk_size', chunkSize);
                formData.append('chunk_overlap', chunkOverlap);
            } else if (filename.endsWith('.csv')) {
                endpoint = '/upload/csv';
                formData.append('file', queueItem.file);
                const groupBy = prompt('Group CSV by column (optional):', '');
                if (groupBy) formData.append('group_by', groupBy);
            } else {
                // TXT, JSON, MD, e tutti i testi plain → /upload/text vuole content:str
                endpoint = '/upload/text';
                const textContent = await this.readFileAsText(queueItem.file);
                formData.append('content', textContent);
                // source_id dal nome file (senza estensione)
                formData.append('source_id', queueItem.file.name.replace(/\.[^.]+$/, ''));
                formData.append('chunk_size', chunkSize);
                formData.append('chunk_overlap', chunkOverlap);
            }

            // Show upload modal
            this.showUploadModal(queueItem.file.name);
            
            // Upload file
            const response = await fetch(this.apiBase + endpoint, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`Upload failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            queueItem.status = 'completed';
            queueItem.progress = 100;
            this.updateUploadQueueUI();
            
            this.hideUploadModal();
            
            // Log activity
            this.logActivity(`Uploaded ${queueItem.file.name} (${result.chunks_processed} chunks)`, 'success');
            
            // Refresh stats
            this.refreshDashboard();
            
            return result;
            
        } catch (error) {
            console.error('Upload failed:', error);
            
            queueItem.status = 'failed';
            this.updateUploadQueueUI();
            
            this.hideUploadModal();
            
            // Show error
            alert(`Upload failed: ${error.message}`);
            
            this.logActivity(`Failed to upload ${queueItem.file.name}`, 'error');
            
            throw error;
        }
    }

    async performSearch() {
        const query = document.getElementById('search-query').value.trim();
        if (!query) return;

        const resultsDiv = document.getElementById('search-results');
        resultsDiv.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-primary"></div>
                <p class="mt-2 text-muted">Ricerca in corso...</p>
            </div>
        `;
        document.getElementById('results-badge').textContent = '…';

        try {
            const formData = new FormData();
            formData.append('query', query);
            formData.append('n_results', document.getElementById('results-count').value);

            const sourceFilter = document.getElementById('source-filter').value;
            if (sourceFilter) formData.append('source_filter', sourceFilter);

            const minSimilarity = parseInt(document.getElementById('min-similarity').value) / 100;
            if (minSimilarity > 0) formData.append('min_similarity', minSimilarity);

            const useReranker = document.getElementById('use-reranker').checked;
            if (useReranker) formData.append('use_reranker', 'true');

            const response = await this.apiCall('/search', { method: 'POST', body: formData });

            this.displaySearchResults(response, query);
            document.getElementById('results-badge').textContent = response.results_count + ' risultati';
            this.logActivity(
                `Ricerca: "${query}" → ${response.results_count} risultati${useReranker ? ' [re-ranked]' : ''}`,
                'info'
            );

        } catch (error) {
            console.error('Search failed:', error);
            document.getElementById('results-badge').textContent = 'errore';
            resultsDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Ricerca fallita: ${error.message}
                </div>
            `;
        }
    }

    displaySearchResults(response, query = '') {
        const resultsDiv = document.getElementById('search-results');
        const useReranker = document.getElementById('use-reranker').checked;

        if (!response.results || response.results.length === 0) {
            resultsDiv.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle me-2"></i>
                    Nessun risultato trovato per la query.
                </div>
            `;
            return;
        }

        let html = '';

        response.results.forEach((result, index) => {
            const similarity = result.similarity !== undefined
                ? Math.round(result.similarity * 100)
                : Math.round((1 - (result.distance || 0)) * 100);

            const barColor = similarity >= 75 ? '#198754' : similarity >= 50 ? '#ffc107' : '#dc3545';
            const badgeClass = similarity >= 75 ? 'success' : similarity >= 50 ? 'warning' : 'danger';
            const rerankerScore = result.rerank_score !== undefined
                ? `<span class="reranker-badge ms-1" title="Re-rank score">↑${result.rerank_score.toFixed(2)}</span>`
                : '';

            const snippet = this.highlightText(
                result.content.substring(0, 400) + (result.content.length > 400 ? '…' : ''),
                query
            );

            html += `
                <div class="card result-card mb-3">
                    <div class="card-body pb-2">
                        <div class="d-flex justify-content-between align-items-start mb-1">
                            <div>
                                <span class="badge bg-${badgeClass}">
                                    ${similarity}% similarità
                                </span>
                                ${rerankerScore}
                                ${useReranker ? '<span class="ms-1 text-muted small">[re-ranked]</span>' : ''}
                            </div>
                            <small class="text-muted text-truncate ms-2" style="max-width:200px;"
                                   title="${result.metadata?.source || ''}">
                                <i class="bi bi-file-earmark me-1"></i>
                                ${result.metadata?.source || 'Sorgente sconosciuta'}
                            </small>
                        </div>
                        <div class="similarity-bar mb-2">
                            <div class="similarity-bar-fill"
                                 style="width:${similarity}%; background:${barColor};"></div>
                        </div>
                        <p class="mb-1 small">${snippet}</p>
                        <small class="text-muted">
                            <i class="bi bi-calendar me-1"></i>
                            ${result.metadata?.timestamp
                                ? new Date(result.metadata.timestamp).toLocaleString('it-IT')
                                : 'Data sconosciuta'}
                        </small>
                    </div>
                </div>
            `;
        });

        resultsDiv.innerHTML = html;
    }

    highlightText(text, query) {
        const escaped = this.escapeHtml(text);
        if (!query) return escaped;
        const terms = query.trim().split(/\s+/).filter(t => t.length > 2);
        if (!terms.length) return escaped;
        const pattern = new RegExp(
            '(' + terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')',
            'gi'
        );
        return escaped.replace(pattern, '<mark>$1</mark>');
    }

    escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ------------------------------------------------------------------
    // RAG Streaming Generation
    // ------------------------------------------------------------------

    async generateRAG() {
        const query = document.getElementById('rag-query').value.trim();
        if (!query) return;

        const responseDiv = document.getElementById('rag-response');
        const statusBadge = document.getElementById('rag-status-badge');
        const tierInfo = document.getElementById('rag-tier-info');
        const tier0Badge = document.getElementById('rag-tier0-badge');
        const tier2Badge = document.getElementById('rag-tier2-badge');
        const fallbackNotice = document.getElementById('rag-fallback-notice');
        const sourcePanel = document.getElementById('rag-source-panel');
        const visualPanel = document.getElementById('rag-visual-panel');
        const btn = document.getElementById('rag-generate-btn');

        // Reset UI
        responseDiv.textContent = '';
        fallbackNotice.classList.add('d-none');
        tierInfo.classList.add('d-none');
        if (sourcePanel) sourcePanel.classList.add('d-none');
        if (visualPanel) visualPanel.classList.add('d-none');
        this.renderRagVisualAssets([]);
        statusBadge.className = 'badge bg-warning';
        statusBadge.textContent = 'Retrieval...';
        if (tier2Badge) {
            tier2Badge.innerHTML = '<i class="bi bi-stars me-1"></i>Tier-2: Magellano';
        }
        btn.disabled = true;

        const formData = new URLSearchParams();
        formData.set('query', query);
        formData.set('n_results', document.getElementById('rag-n-results').value);
        formData.set('temperature', document.getElementById('rag-temperature').value);
        formData.set('max_tokens', document.getElementById('rag-max-tokens').value);
        const visualIntent = this.isRagVisualRequest(query);

        try {
            this._ragAbortController = new AbortController();

            const response = await fetch('/rag/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData.toString(),
                signal: this._ragAbortController.signal,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'HTTP ' + response.status }));
                throw new Error(err.detail || 'HTTP ' + response.status);
            }

            statusBadge.className = 'badge bg-primary';
            statusBadge.textContent = 'Generazione...';

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let text = '';
            let visualAssets = [];
            let visualGuard = this.buildRagVisualGuard([]);

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ')) continue;

                    const payload = trimmed.slice(6);
                    if (payload === '[DONE]') {
                        statusBadge.className = 'badge bg-success';
                        statusBadge.textContent = 'Completato';
                        this.logActivity(`RAG: "${query.substring(0,40)}..." generato`, 'success');
                        break;
                    }

                    try {
                        const obj = JSON.parse(payload);
                        if (obj.type === 'retrieval') {
                            const retrievedChunks = obj.chunks || [];
                            const contextChunks = obj.context_chunks || retrievedChunks;
                            const sourceCount = Array.isArray(obj.sources) ? obj.sources.length : 0;
                            const contextCount = Number.isFinite(Number(obj.context_count))
                                ? Number(obj.context_count)
                                : contextChunks.length;
                            const generation = obj.generation || {};
                            const maxTokens = generation.max_tokens || document.getElementById('rag-max-tokens').value;
                            const temperature = generation.temperature !== undefined
                                ? Number(generation.temperature).toFixed(1)
                                : Number(document.getElementById('rag-temperature').value).toFixed(1);
                            tier0Badge.innerHTML =
                                `<i class="bi bi-database me-1"></i>Tier-0: ${obj.count} chunks / ${contextCount} al modello${sourceCount ? ` / ${sourceCount} fonti` : ''}`;
                            if (tier2Badge) {
                                tier2Badge.innerHTML =
                                    `<i class="bi bi-stars me-1"></i>Tier-2: Magellano - ${maxTokens} tok - T ${temperature}`;
                            }
                            tierInfo.classList.remove('d-none');
                            this.renderRagSources(retrievedChunks, obj.sources || []);
                            visualGuard = this.buildRagVisualGuard(contextChunks);
                            visualAssets = visualIntent
                                ? this.mergeRagVisualAssets(
                                    visualAssets,
                                    this.collectRagVisualAssets(contextChunks, visualGuard)
                                )
                                : [];
                            this.renderRagVisualAssets(visualAssets);

                        } else if (obj.type === 'token') {
                            text += obj.text;
                            const extracted = this.extractRagVisualAssets(text);
                            visualAssets = this.mergeRagVisualAssets(
                                visualAssets,
                                visualIntent ? this.filterRagVisualAssets(extracted.assets, visualGuard) : []
                            );
                            this.renderRagVisualAssets(visualAssets);
                            responseDiv.textContent = extracted.cleanedText;
                            responseDiv.scrollTop = responseDiv.scrollHeight;

                        } else if (obj.type === 'error') {
                            throw new Error(obj.message);
                        }
                    } catch (parseErr) {
                        // not valid JSON — treat as raw token
                        if (typeof payload === 'string' && payload !== '[DONE]') {
                            text += payload;
                            const extracted = this.extractRagVisualAssets(text);
                            visualAssets = this.mergeRagVisualAssets(
                                visualAssets,
                                visualIntent ? this.filterRagVisualAssets(extracted.assets, visualGuard) : []
                            );
                            this.renderRagVisualAssets(visualAssets);
                            responseDiv.textContent = extracted.cleanedText;
                        }
                    }
                }
            }

            // Detect fallback message from Magellano-unavailable token
            if (text.includes('non raggiungibile') || text.includes('[Errore Magellano')) {
                fallbackNotice.classList.remove('d-none');
                statusBadge.className = 'badge bg-warning';
                statusBadge.textContent = 'Fallback';
            }

        } catch (error) {
            if (error.name === 'AbortError') {
                statusBadge.className = 'badge bg-secondary';
                statusBadge.textContent = 'Interrotto';
            } else {
                console.error('RAG stream error:', error);
                statusBadge.className = 'badge bg-danger';
                statusBadge.textContent = 'Errore';
                if (error.message.includes('503') || error.message.includes('not available')) {
                    fallbackNotice.classList.remove('d-none');
                    responseDiv.textContent = '[Magellano non disponibile — servizio offline]';
                } else {
                    responseDiv.textContent = `[Errore: ${error.message}]`;
                }
                this.logActivity('RAG stream fallito: ' + error.message, 'error');
            }
        } finally {
            btn.disabled = false;
            this._ragAbortController = null;
        }
    }

    renderRagSources(chunks = [], sources = []) {
        const panel = document.getElementById('rag-source-panel');
        const list = document.getElementById('rag-source-list');
        const count = document.getElementById('rag-source-count');
        if (!panel || !list || !count) return;

        const hasChunks = Array.isArray(chunks) && chunks.length > 0;
        const hasSources = Array.isArray(sources) && sources.length > 0;
        if (!hasChunks && !hasSources) {
            panel.classList.add('d-none');
            list.innerHTML = '';
            count.textContent = '0 fonti';
            return;
        }

        const uniqueSourceCount = hasSources
            ? sources.length
            : new Set(chunks.map(c => c.source || c.label || c.id).filter(Boolean)).size;
        count.textContent = `${uniqueSourceCount} font${uniqueSourceCount === 1 ? 'e' : 'i'}`;

        if (hasChunks) {
            list.innerHTML = chunks.map(chunk => {
                const label = this.escapeHtml(chunk.label || this.formatRagSourceLabel(chunk));
                const meta = this.escapeHtml(this.formatRagSourceMeta(chunk));
                const preview = this.escapeHtml(this.normalizeRagTextArtifacts(chunk.preview || ''));
                const score = this.formatRagSimilarity(chunk.similarity);
                return `
                    <div class="rag-source-item">
                        <div class="rag-source-title">
                            <span class="rag-source-label" title="${label}">
                                <i class="bi bi-file-earmark-text me-1"></i>${label}
                            </span>
                            ${score}
                        </div>
                        ${meta ? `<div class="rag-source-meta">${meta}</div>` : ''}
                        ${preview ? `<div class="rag-source-preview">${preview}</div>` : ''}
                    </div>
                `;
            }).join('');
        } else {
            list.innerHTML = sources.map(source => `
                <div class="rag-source-item">
                    <div class="rag-source-title">
                        <span class="rag-source-label" title="${this.escapeHtml(source)}">
                            <i class="bi bi-file-earmark-text me-1"></i>${this.escapeHtml(source)}
                        </span>
                    </div>
                </div>
            `).join('');
        }

        panel.classList.remove('d-none');
    }

    isRagVisualRequest(query = '') {
        return /\b(visualizza|visualizzare|mostra|mostrare|vedi|apri|render|renderizza|immagin[ei]|figur[ae]|grafic[oi]|tabell[ae]|formula|formule|pagina|asset|screenshot)\b/i
            .test(String(query || ''));
    }

    buildRagVisualGuard(chunks = []) {
        const rows = (chunks || [])
            .map((chunk, index) => {
                const source = chunk.source || chunk.filename || chunk.document || chunk.id || '';
                const sourceKey = this.normalizeRagSourceKey(source);
                const page = this.normalizeRagPage(chunk.page ?? chunk.page_number ?? chunk.visual_page);
                const similarity = this.coerceRagSimilarity(chunk);
                return {
                    sourceKey,
                    page,
                    pageKey: this.sourcePageKey(sourceKey, page),
                    rank: index + 1,
                    similarity,
                };
            })
            .filter(row => row.sourceKey);

        const similarities = rows
            .map(row => row.similarity)
            .filter(value => Number.isFinite(value));
        const maxSimilarity = similarities.length ? Math.max(...similarities) : null;
        const minSimilarity = maxSimilarity !== null ? Math.max(0, maxSimilarity - 0.08) : null;
        const maxStrongRank = Math.min(5, Math.max(rows.length, 1));
        const strongRows = rows.filter(row => {
            const rankStrong = row.rank <= maxStrongRank;
            const scoreStrong = minSimilarity !== null
                && Number.isFinite(row.similarity)
                && row.similarity >= minSimilarity;
            return rankStrong || scoreStrong;
        });

        return {
            active: rows.length > 0,
            minSimilarity,
            maxStrongRank,
            allSourceKeys: new Set(rows.map(row => row.sourceKey)),
            allSourcePageKeys: new Set(rows.map(row => row.pageKey).filter(Boolean)),
            strongSourceKeys: new Set(strongRows.map(row => row.sourceKey)),
            strongSourcePageKeys: new Set(strongRows.map(row => row.pageKey).filter(Boolean)),
        };
    }

    collectRagVisualAssets(chunks = [], guard = null) {
        const assets = [];
        chunks.forEach((chunk, index) => {
            const similarity = this.coerceRagSimilarity(chunk);
            [
                ['image_url', chunk.image_url],
                ['page_image_url', chunk.page_image_url],
                ['visual_url', chunk.visual_url],
                ['asset_path', chunk.asset_path],
            ].forEach(([kind, value]) => {
                if (!value) return;
                const url = this.normalizeRagVisualUrl(value);
                if (!url) return;
                const meta = this.extractRagVisualRefMeta(value);
                const asset = {
                    url,
                    raw: String(value),
                    kind,
                    label: chunk.label || chunk.source || `chunk_${chunk.index || index + 1}`,
                    source: chunk.source || chunk.filename || meta.source || '',
                    page: chunk.page ?? chunk.page_number ?? meta.page,
                    rank: index + 1,
                    similarity,
                };
                if (this.isRagVisualAssetAllowed(asset, guard)) assets.push(asset);
            });
        });
        return assets;
    }

    filterRagVisualAssets(assets = [], guard = null) {
        return (assets || []).filter(asset => this.isRagVisualAssetAllowed(asset, guard));
    }

    isRagVisualAssetAllowed(asset, guard = null) {
        if (!asset || !asset.url) return false;
        if (!guard || !guard.active) return true;

        const meta = this.extractRagVisualRefMeta(asset.url || asset.raw || '');
        const sourceKeys = new Set([
            asset.source,
            asset.visual_source,
            meta.source,
            asset.label,
            asset.raw,
            asset.url,
        ].map(value => this.normalizeRagSourceKey(value)).filter(Boolean));
        const page = this.normalizeRagPage(asset.page ?? asset.visual_page ?? meta.page);
        const rank = Number(asset.rank);
        const similarity = Number(asset.similarity);

        if (!sourceKeys.size) return false;

        for (const sourceKey of sourceKeys) {
            const pageKey = this.sourcePageKey(sourceKey, page);
            if (pageKey && guard.strongSourcePageKeys.has(pageKey)) return true;
        }

        for (const sourceKey of sourceKeys) {
            if (!guard.strongSourceKeys.has(sourceKey)) continue;

            const rankStrong = Number.isFinite(rank) && rank <= guard.maxStrongRank;
            const scoreStrong = Number.isFinite(similarity)
                && guard.minSimilarity !== null
                && similarity >= guard.minSimilarity;
            const fromAnswer = !Number.isFinite(rank);
            if (rankStrong || scoreStrong || fromAnswer) return true;
        }

        return false;
    }

    coerceRagSimilarity(chunk = {}) {
        const direct = chunk.similarity ?? chunk.score ?? chunk.relevance;
        const directNumber = Number(direct);
        if (Number.isFinite(directNumber)) return directNumber;

        const distance = Number(chunk.distance);
        if (Number.isFinite(distance)) return 1 - distance;
        return null;
    }

    sourcePageKey(sourceKey, page) {
        const normalizedSource = String(sourceKey || '').trim();
        const normalizedPage = this.normalizeRagPage(page);
        if (!normalizedSource || !normalizedPage) return '';
        return `${normalizedSource}#${normalizedPage}`;
    }

    normalizeRagPage(value) {
        if (value === undefined || value === null || value === '') return '';
        const match = String(value).match(/\d+/);
        if (!match) return '';
        return String(parseInt(match[0], 10));
    }

    normalizeRagSourceKey(value) {
        let raw = String(value || '').trim();
        if (!raw) return '';

        raw = this.decodeRagComponent(raw).replace(/\\/g, '/');

        const urlMeta = this.extractRagVisualRefMeta(raw, false);
        if (urlMeta.source && urlMeta.source !== raw) {
            raw = String(urlMeta.source);
        }

        raw = this.decodeRagComponent(raw).replace(/\\/g, '/');
        const pdfPagesMatch = raw.match(/(?:^|\/)pdf_pages\/([^\/?#]+)/i);
        if (pdfPagesMatch) raw = pdfPagesMatch[1];

        raw = raw
            .replace(/[?#].*$/, '')
            .replace(/,\s*pag\.\s*\d+.*$/i, '')
            .replace(/\/+$/, '');

        if (raw.includes('/')) raw = raw.split('/').pop();

        raw = raw
            .replace(/_pdf_[0-9a-f]{6,}$/i, '')
            .replace(/\.pdf_[0-9a-f]{6,}$/i, '.pdf')
            .replace(/\.(?:pdf|png|jpe?g|webp|gif|svg)$/i, '')
            .replace(/^page[_-]?\d+$/i, '');

        return raw.toLowerCase().replace(/[^a-z0-9]+/g, '');
    }

    extractRagVisualRefMeta(value, parseNested = true) {
        let raw = String(value || '').trim();
        if (!raw) return {};

        raw = raw.replace(/^["'<(]+|[>"'\]),.;]+$/g, '');
        const decoded = this.decodeRagComponent(raw).replace(/\\/g, '/');
        const meta = {};

        try {
            if (/^(?:https?:)?\/\//i.test(raw) || raw.startsWith('/')) {
                const url = new URL(raw, window.location.origin);
                const source = url.searchParams.get('source');
                const page = url.searchParams.get('page');
                const path = url.searchParams.get('path');
                if (source) meta.source = source;
                if (page) meta.page = page;
                if (path && parseNested) {
                    const pathMeta = this.extractRagVisualRefMeta(path, false);
                    meta.source = meta.source || pathMeta.source || path;
                    meta.page = meta.page || pathMeta.page;
                }
                if (meta.source || meta.page) return meta;
            }
        } catch (error) {
            // Fall through to path heuristics.
        }

        const pageImageMatch = decoded.match(/(?:^|\/)pdf_pages\/([^\/?#]+)\/page[_-]?(\d+)\.(?:png|jpe?g|webp|gif|svg)/i);
        if (pageImageMatch) {
            return {
                source: pageImageMatch[1],
                page: pageImageMatch[2],
            };
        }

        const pdfMatch = decoded.match(/([^\/?#]+\.pdf)(?:[?#].*)?$/i);
        if (pdfMatch) meta.source = pdfMatch[1];

        const pageMatch = decoded.match(/(?:^|[^\w])page[_-]?(\d+)\.(?:png|jpe?g|webp|gif|svg)/i);
        if (pageMatch) meta.page = pageMatch[1];

        return meta;
    }

    decodeRagComponent(value) {
        let decoded = String(value || '').trim();
        for (let i = 0; i < 2; i += 1) {
            try {
                const next = decodeURIComponent(decoded);
                if (next === decoded) break;
                decoded = next;
            } catch (error) {
                break;
            }
        }
        return decoded;
    }

    normalizeRagTextArtifacts(text) {
        let value = String(text || '');
        if (!value) return '';
        value = value
            .replace(/([A-Za-z])\s*\u019f(?=[A-Za-z])/g, '$1ti')
            .replace(/([A-Za-z])\s*\u01ab(?=[A-Za-z]|\b)/g, '$1tti')
            .replace(/([A-Za-z])\s*\u01a9(?=[A-Za-z])/g, '$1tt');
        const replacements = {
            '\ufb00': 'ff',
            '\ufb01': 'fi',
            '\ufb02': 'fl',
            '\ufb03': 'ffi',
            '\ufb04': 'ffl',
            '\ufb05': 'st',
            '\ufb06': 'st',
            '\u00ad': '',
            '\u200b': '',
            '\u200c': '',
            '\u200d': '',
            '\u2212': '-',
            '\u2010': '-',
            '\u2011': '-',
            '\u2012': '-',
            '\u2013': '-',
            '\u2014': '-',
            '\u2044': '/',
            '\u0131': 'i',
            '\u00c3\u00a0': 'à',
            '\u00c3\u00a8': 'è',
            '\u00c3\u00a9': 'é',
            '\u00c3\u00ac': 'ì',
            '\u00c3\u00b2': 'ò',
            '\u00c3\u00b9': 'ù',
            '\u00c2\u00b0': '°',
            '\u00c2\u00b1': '±',
            '\u00e2\u0080\u0098': "'",
            '\u00e2\u0080\u0099': "'",
            '\u00e2\u0080\u009c': '"',
            '\u00e2\u0080\u009d': '"',
            '\u00e2\u0080\u0093': '-',
            '\u00e2\u0080\u0094': '-',
            '\u00e2\u0080\u00a2': '-',
            '\u00ef\u0082\u00a1': '-',
            '\u00ef\u0082\u00b7': '-',
            '\u00e2\u0082\u00ac': '€',
            '\u00e2\u0088\u0092': '-',
            '\u00e2\u0088\u0091': '\u2211',
            '\u00e2\u0088\u0098': '\u2218',
            '\u00e2\u0088\u00ab': '\u222b',
            '\u00e2\u0089\u0088': '\u2248',
            '\u00e2\u2030\u00a4': '≤',
            '\u00e2\u2030\u00a5': '≥',
            '\u00e2\u0089\u00a4': '\u2264',
            '\u00e2\u0089\u00a5': '\u2265',
            '\u00e2\u008b\u0085': '\u22c5',
            '\u00cf\u0080': '\u03c0',
            '\u00cf\u0086': '\u03c6',
            '\u00cf\u0088': '\u03c8',
            '\u00ce\u00a6': '\u03a6',
            '\u00ce\u00a3': '\u03a3',
            '\u00c6\u009f': '\u019f',
            '\u00c6\u00ab': '\u01ab',
            '\u00c6\u00a9': '\u01a9',
            '\u00ef\u00ac\u0081': 'fi',
        };
        Object.entries(replacements).forEach(([from, to]) => {
            value = value.split(from).join(to);
        });
        if (value.normalize) value = value.normalize('NFKC');
        value = value
            .replace(/([A-Za-z])\s*\u019f(?=[A-Za-z])/g, '$1ti')
            .replace(/([A-Za-z])\s*\u01ab(?=[A-Za-z]|\b)/g, '$1tti')
            .replace(/([A-Za-z])\s*\u01a9(?=[A-Za-z])/g, '$1tt');
        return value
            .replace(/[ \t\f\v]+/g, ' ')
            .replace(/ *\n */g, '\n')
            .replace(/\n{3,}/g, '\n\n')
            .trimEnd();
    }

    extractRagVisualAssets(text) {
        const assets = [];
        const cleanedLines = [];
        const visualLine = /^\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?(?:Asset visuale|Visual asset|Immagine|Image|VISUAL_ASSET(?:\s+\w+)?)\s*:\s*(.+)$/i;
        const urlPattern = /(https?:\/\/[^\s<>"']+|data:image\/[^\s<>"']+|\/[^\s<>"']+|[A-Za-z]:\\[^\s<>"']+|[\w./\\-]+\.(?:png|jpe?g|webp|gif|svg))/gi;

        this.normalizeRagTextArtifacts(text).split('\n').forEach(line => {
            const match = line.match(visualLine);
            if (!match) {
                cleanedLines.push(line);
                return;
            }

            const matches = match[1].match(urlPattern) || [];
            const citation = this.parseRagSourceCitation(match[1]);
            matches.forEach((raw, index) => {
                const url = this.normalizeRagVisualUrl(raw);
                if (url) {
                    const meta = this.extractRagVisualRefMeta(raw);
                    assets.push({
                        url,
                        raw: String(raw).trim(),
                        kind: 'asset_visuale',
                        label: index === 0 ? 'Asset visuale' : `Asset visuale ${index + 1}`,
                        source: citation.source || meta.source || '',
                        page: citation.page || meta.page || '',
                        similarity: citation.similarity,
                    });
                }
            });
        });

        return { cleanedText: cleanedLines.join('\n').trimEnd(), assets };
    }

    parseRagSourceCitation(value) {
        const text = String(value || '');
        const match = text.match(/\[fonte:\s*([^\]]+)\]/i);
        if (!match) return {};

        let citation = match[1].trim();
        let similarity = null;
        const simMatch = citation.match(/,\s*sim\s*([0-9.]+)/i);
        if (simMatch) {
            similarity = Number(simMatch[1]);
            citation = citation.replace(simMatch[0], '').trim();
        }

        let page = '';
        const pageMatch = citation.match(/,\s*pag\.\s*([^,]+)\s*$/i);
        if (pageMatch) {
            page = pageMatch[1].trim();
            citation = citation.slice(0, pageMatch.index).trim();
        }

        return {
            source: citation,
            page,
            similarity: Number.isFinite(similarity) ? similarity : null,
        };
    }

    normalizeRagVisualUrl(value) {
        let raw = String(value || '').trim();
        raw = raw.replace(/^["'<(]+|[>"'\]),.;]+$/g, '');
        if (!raw) return '';
        if (!this.isLikelyRagVisualRef(raw)) return '';
        if (/^https?:\/\//i.test(raw) || /^data:image\//i.test(raw)) {
            return raw;
        }
        if (raw.startsWith('/visual/') || raw.startsWith('/static/')) return raw;
        return `/visual/asset?path=${encodeURIComponent(raw)}`;
    }

    isLikelyRagVisualRef(value) {
        const raw = String(value || '').trim();
        if (!raw) return false;
        if (/^data:image\//i.test(raw)) return true;
        if (/^https?:\/\//i.test(raw)) {
            return /\/(?:visual|static)\//i.test(raw)
                || /\.(?:png|jpe?g|webp|gif|svg)(?:[?#].*)?$/i.test(raw)
                || /[?&](?:path|source)=/i.test(raw);
        }
        if (/^\/(?:visual|static)\//i.test(raw)) return true;
        if (/^[A-Za-z]:\\.*\.(?:png|jpe?g|webp|gif|svg)(?:[?#].*)?$/i.test(raw)) return true;
        if (/^\/.*\.(?:png|jpe?g|webp|gif|svg)(?:[?#].*)?$/i.test(raw)) return true;
        if (/^[\w./\\-]+\.(?:png|jpe?g|webp|gif|svg)(?:[?#].*)?$/i.test(raw)) return true;
        return false;
    }

    mergeRagVisualAssets(existing = [], incoming = []) {
        const byUrl = new Map();
        existing.concat(incoming).forEach(asset => {
            if (!asset || !asset.url) return;
            if (!byUrl.has(asset.url)) byUrl.set(asset.url, asset);
        });
        return Array.from(byUrl.values());
    }

    renderRagVisualAssets(assets = []) {
        const panel = document.getElementById('rag-visual-panel');
        const list = document.getElementById('rag-visual-list');
        const count = document.getElementById('rag-visual-count');
        if (!panel || !list || !count) return;

        if (!assets.length) {
            panel.classList.add('d-none');
            list.innerHTML = '';
            count.textContent = '0 asset';
            return;
        }

        count.textContent = `${assets.length} asset`;
        list.innerHTML = assets.map(asset => {
            const url = this.escapeHtml(asset.url);
            const label = this.escapeHtml(asset.label || asset.kind || 'Asset visuale');
            const raw = this.escapeHtml(asset.raw || asset.url);
            return `
                <div class="rag-visual-item">
                    <img src="${url}" alt="${label}" loading="lazy">
                    <div class="rag-visual-caption">
                        <div class="fw-semibold">${label}</div>
                        <a href="${url}" target="_blank" rel="noopener noreferrer">${raw}</a>
                    </div>
                </div>
            `;
        }).join('');
        panel.classList.remove('d-none');
    }

    formatRagSourceLabel(chunk) {
        const parts = [chunk.source || chunk.id || `chunk_${chunk.index || '?'}`];
        if (chunk.page !== undefined && chunk.page !== null) parts.push(`pag. ${chunk.page}`);
        if (chunk.section) parts.push(`sezione ${chunk.section}`);
        if (chunk.row_range_start !== undefined || chunk.row_range_end !== undefined) {
            const start = chunk.row_range_start ?? '?';
            const end = chunk.row_range_end ?? '?';
            parts.push(`righe ${start}-${end}`);
        }
        if (chunk.group_by) parts.push(`${chunk.group_by}: ${chunk.group_value || ''}`);
        return parts.join(', ');
    }

    formatRagSourceMeta(chunk) {
        const parts = [];
        if (chunk.type) parts.push(chunk.type);
        if (chunk.structured_kind) parts.push(chunk.structured_kind);
        if (chunk.table_title) parts.push(chunk.table_title);
        if (chunk.table_row_count !== undefined) parts.push(`${chunk.table_row_count} righe`);
        if (chunk.columns) parts.push(`colonne ${chunk.columns}`);
        if (chunk.formula_count !== undefined) parts.push(`${chunk.formula_count} formule`);
        if (chunk.formula) parts.push('formula');
        if (chunk.image_url || chunk.page_image_url || chunk.visual_url || chunk.asset_path) {
            parts.push('asset visuale');
        }
        if (chunk.id && chunk.id !== chunk.source) parts.push(`id ${chunk.id}`);
        return parts.join(' - ');
    }

    formatRagSimilarity(value) {
        if (value === undefined || value === null || Number.isNaN(Number(value))) {
            return '<span class="badge bg-light text-dark border">score n/d</span>';
        }
        const percent = Math.max(0, Math.min(100, Math.round(Number(value) * 100)));
        const badge = percent >= 75 ? 'success' : percent >= 45 ? 'warning text-dark' : 'secondary';
        return `<span class="badge bg-${badge}">${percent}%</span>`;
    }

    stopRAG() {
        if (this._ragAbortController) {
            this._ragAbortController.abort();
        }
    }

    async runBenchmark() {
        if (!confirm('Run performance benchmark? This may take a few seconds.')) {
            return;
        }
        
        try {
            const response = await this.apiCall('/embeddings/benchmark?sample_size=100&iterations=3');
            
            alert(`
                Benchmark Results:
                ------------------
                Throughput: ${response.benchmark_results.throughput_docs_per_sec} docs/sec
                Latency: ${response.benchmark_results.time_per_doc_ms} ms per document
                Device: ${response.benchmark_results.device}
                
                Recommendation: ${response.recommendation}
            `);
            
            this.logActivity('Ran performance benchmark', 'info');
            this.refreshDashboard();
            
        } catch (error) {
            alert('Benchmark failed: ' + error.message);
        }
    }

    async viewDLQ() {
        try {
            const response = await this.apiCall('/dlq/failed-chunks?limit=10');
            
            if (!response.chunks || response.chunks.length === 0) {
                alert('No failed chunks in DLQ');
                return;
            }
            
            let html = '<h6>Failed Chunks in DLQ:</h6>';
            
            response.chunks.forEach(chunk => {
                const timeAgo = this.timeAgo(chunk.failed_at);
                
                html += `
                    <div class="card result-card mb-2">
                        <div class="card-body py-2">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <small class="text-muted">${timeAgo}</small>
                                    <p class="mb-1 fw-bold">${chunk.chunk_id}</p>
                                    <p class="mb-1 small text-danger">${chunk.error}</p>
                                    <span class="badge bg-warning">${chunk.reason}</span>
                                </div>
                                <button class="btn btn-sm btn-outline-primary" onclick="retryChunk('${chunk.id}')">
                                    <i class="bi bi-arrow-clockwise"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            // Show in DLQ details area
            const dlqDetails = document.getElementById('dlq-details');
            if (dlqDetails) dlqDetails.innerHTML = html;
            document.getElementById('search-results').innerHTML = html;
            
            this.logActivity('Viewed DLQ failed chunks', 'info');
            
        } catch (error) {
            alert('Failed to load DLQ: ' + error.message);
        }
    }

    async retryAllFailed() {
        if (!confirm('Retry all failed chunks?')) {
            return;
        }
        
        try {
            const response = await this.apiCall('/dlq/failed-chunks?limit=100');
            
            if (!response.chunks || response.chunks.length === 0) {
                alert('No failed chunks to retry');
                return;
            }
            
            let retried = 0;
            for (const chunk of response.chunks) {
                if (chunk.status === 'pending') {
                    await this.apiCall(`/dlq/retry/${chunk.id}`, { method: 'POST' });
                    retried++;
                }
            }
            
            alert(`Retry initiated for ${retried} chunks`);
            this.logActivity(`Retried ${retried} failed chunks`, 'info');
            this.refreshDashboard();
            
        } catch (error) {
            alert('Failed to retry chunks: ' + error.message);
        }
    }

    async clearDLQ() {
        if (!confirm('Clear all permanent failures from DLQ?')) {
            return;
        }
        
        try {
            const response = await this.apiCall('/dlq/clear-permanent', { method: 'DELETE' });
            
            alert(`Cleared ${response.deleted_count} permanent failures`);
            this.logActivity(`Cleared ${response.deleted_count} permanent failures from DLQ`, 'info');
            this.refreshDashboard();
            
        } catch (error) {
            alert('Failed to clear DLQ: ' + error.message);
        }
    }

    async loadSources() {
        try {
            const response = await this.apiCall('/documents?limit=500');
            const sources = [...new Set(
                (response.documents || [])
                    .map(d => d.source_id)
                    .filter(Boolean)
            )];
            const select = document.getElementById('source-filter');
            select.innerHTML = '<option value="">Tutte le sorgenti</option>';
            sources.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s.length > 40 ? s.substring(0, 38) + '…' : s;
                opt.title = s;
                select.appendChild(opt);
            });
        } catch (e) {
            console.warn('Could not load sources:', e);
        }
    }

    setupCharts() {
        const chartConfig = {
            type: 'doughnut',
            data: {
                labels: ['Pending', 'Retrying', 'Resolved'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: [
                        'rgba(220, 53, 69, 0.8)',
                        'rgba(255, 193, 7, 0.8)',
                        'rgba(25, 135, 84, 0.8)'
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                cutout: '70%'
            }
        };

        // DLQ Chart (dashboard tab)
        const dlqCtx = document.getElementById('dlqChart').getContext('2d');
        this.charts.dlq = new Chart(dlqCtx, JSON.parse(JSON.stringify(chartConfig)));

        // DLQ Chart (DLQ tab)
        const dlqCtx2 = document.getElementById('dlqChart2').getContext('2d');
        this.charts.dlq2 = new Chart(dlqCtx2, JSON.parse(JSON.stringify(chartConfig)));
    }


    updateDLQChart(dlqStats) {
        const chunkStats = dlqStats?.failed_chunks || {};
        const data = [
            chunkStats.pending || 0,
            chunkStats.retrying || 0,
            chunkStats.resolved || 0
        ];
        if (this.charts.dlq) {
            this.charts.dlq.data.datasets[0].data = data;
            this.charts.dlq.update();
        }
        if (this.charts.dlq2) {
            this.charts.dlq2.data.datasets[0].data = data;
            this.charts.dlq2.update();
        }
    }

    showUploadModal(filename) {
        document.getElementById('upload-filename').textContent = filename;
        document.getElementById('upload-progress-bar').style.width = '0%';
        document.getElementById('upload-status').textContent = 'Starting upload...';
        
        const modal = new bootstrap.Modal(document.getElementById('uploadModal'));
        modal.show();
        
        // Simulate progress
        let progress = 0;
        const interval = setInterval(() => {
            progress += 5;
            document.getElementById('upload-progress-bar').style.width = progress + '%';
            
            if (progress >= 30) {
                document.getElementById('upload-status').textContent = 'Processing...';
            }
            
            if (progress >= 100) {
                clearInterval(interval);
                setTimeout(() => {
                    modal.hide();
                }, 500);
            }
        }, 200);
    }

    hideUploadModal() {
        const modal = bootstrap.Modal.getInstance(document.getElementById('uploadModal'));
        if (modal) {
            modal.hide();
        }
    }

    logActivity(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const typeIcon = {
            'info': 'bi-info-circle',
            'success': 'bi-check-circle',
            'warning': 'bi-exclamation-triangle',
            'error': 'bi-x-circle'
        }[type] || 'bi-info-circle';
        
        const typeColor = {
            'info': 'primary',
            'success': 'success',
            'warning': 'warning',
            'error': 'danger'
        }[type] || 'secondary';
        
        this.activityLog.unshift({
            timestamp,
            message,
            type,
            typeIcon,
            typeColor
        });
        
        // Keep only last 10 activities
        if (this.activityLog.length > 10) {
            this.activityLog.pop();
        }
        
        this.updateActivityLog();
    }

    updateActivityLog() {
        const timeline = document.getElementById('activity-timeline');
        
        let html = '';
        this.activityLog.forEach(activity => {
            html += `
                <div class="timeline-item mb-3">
                    <div class="timeline-marker bg-${activity.typeColor}"></div>
                    <div class="timeline-content">
                        <small class="text-muted">${activity.timestamp}</small>
                        <p class="mb-0">
                            <i class="bi ${activity.typeIcon} me-1 text-${activity.typeColor}"></i>
                            ${activity.message}
                        </p>
                    </div>
                </div>
            `;
        });
        
        timeline.innerHTML = html;
    }

    async apiCall(endpoint, options = {}) {
        const url = this.apiBase + endpoint;
        
        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json',
                ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' })
            },
            ...options
        });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        return response.json();
    }

    formatUptime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        return `${hours}h ${minutes}m ${secs}s`;
    }

    timeAgo(timestamp) {
        const now = new Date();
        const past = new Date(timestamp);
        const diffMs = now - past;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffDays > 0) {
            return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
        } else if (diffHours > 0) {
            return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        } else if (diffMins > 0) {
            return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        } else {
            return 'just now';
        }
    }
}

// Helper functions per sliders
function updateSliderValue(sliderId, displayId, isPercentage = false) {
    const slider = document.getElementById(sliderId);
    const display = document.getElementById(displayId);
    
    if (isPercentage) {
        display.textContent = slider.value + '%';
    } else {
        display.textContent = slider.value + ' chars';
    }
}

// Funzioni globali
async function retryChunk(chunkId) {
    try {
        const response = await fetch(`/dlq/retry/${chunkId}`, { method: 'POST' });
        const result = await response.json();
        
        alert(`Retry initiated: ${result.message}`);
        window.dashboard.logActivity(`Retried chunk ${chunkId}`, 'info');
        window.dashboard.refreshDashboard();
        
    } catch (error) {
        alert('Retry failed: ' + error.message);
    }
}

function viewChunkDetails(chunkId) {
    alert(`Chunk details for: ${chunkId}\n\nFeature to be implemented in future version.`);
}

function showApiSpec() {
    fetch('/api-spec')
        .then(response => response.json())
        .then(spec => {
            alert(`API Specification:\n\nVersion: ${spec.version}\n\nEndpoints:\n${
                spec.endpoints.map(e => `• ${e.method} ${e.path} - ${e.description}`).join('\n')
            }`);
        })
        .catch(error => {
            alert('Failed to load API spec: ' + error.message);
        });
}

// Inizializza dashboard
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new VectorDashboard();
});
