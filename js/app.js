document.addEventListener('DOMContentLoaded', () => {
    'use strict';
  
    // Linked directly to your live Render backend
    const API_BASE = (window.API_BASE || 'https://project-stride-2026.onrender.com').replace(/\/+$/, '');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  
    // --- Utilities ---
    const peso = (n) => '\u20B1' + Number(n || 0).toLocaleString('en-PH');
    const $ = (id) => document.getElementById(id);
    const setText = (id, val) => { const el = $(id); if (el) el.textContent = val; };
    const getVal = (id) => { const el = $(id); return el ? el.value.trim() : ''; };
    
    function setBusy(btn, busy, label) {
      if (!btn) return;
      btn.disabled = busy;
      if (label != null) btn.textContent = label;
      btn.style.opacity = busy ? '0.6' : '1';
      btn.style.cursor = busy ? 'not-allowed' : 'pointer';
    }
  
    // --- Fetch with timeout + retry ---
    function fetchWithTimeout(url, opts, timeoutMs) {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), timeoutMs);
      return fetch(url, Object.assign({}, opts, { signal: controller.signal }))
        .finally(() => clearTimeout(id));
    }
  
    async function fetchJsonWithRetry(url, { attempts = 4, timeoutMs = 15000, baseDelayMs = 900 } = {}) {
      let lastErr;
      for (let i = 0; i < attempts; i++) {
        try {
          const res = await fetchWithTimeout(url, {}, timeoutMs);
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return await res.json();
        } catch (err) {
          lastErr = err;
          if (i < attempts - 1) {
            const delay = baseDelayMs * Math.pow(1.6, i);
            await new Promise((r) => setTimeout(r, delay));
          }
        }
      }
      throw lastErr;
    }
  
    const openModal = (el) => { if (!el) return; el.classList.remove('hidden'); document.body.classList.add('modal-active'); };
    const closeModal = (el) => { if (!el) return; el.classList.add('hidden'); document.body.classList.remove('modal-active'); };
  
    // --- State Variables ---
    let pendingPayload = null;   
    let currentBooking = null;   
  
    // --- Form Elements ---
    const form = $('register-form');
    const pkgSel = $('package');
    const runnerNamesWrap = $('runner-names');
    const estimatedTotal = $('estimated-total');

    function currentPax() {
        if (!pkgSel) return 1;
        const opt = pkgSel.options[pkgSel.selectedIndex];
        return parseInt(opt.getAttribute('data-pax') || '1', 10);
    }
    
    function currentPrice() {
        if (!pkgSel) return 0;
        const opt = pkgSel.options[pkgSel.selectedIndex];
        return parseInt(opt.getAttribute('data-price') || '0', 10);
    }

    function updateEstimate() {
        const total = currentPrice();
        if (estimatedTotal) estimatedTotal.textContent = peso(total);
    }

    function currentRunnerNames() {
      if (!runnerNamesWrap) return [];
      return Array.prototype.map.call(
        runnerNamesWrap.querySelectorAll('input.runner-name-input'),
        function (el) { return el.value.trim(); }
      );
    }

    function renderRunnerNameFields() {
      if (!runnerNamesWrap || !pkgSel) return;
      const n = currentPax();
      const existing = currentRunnerNames();
      runnerNamesWrap.innerHTML = '';
      
      for (let i = 0; i < n; i++) {
        const wrap = document.createElement('div');
        wrap.className = 'relative mb-3';
        const input = document.createElement('input');
        input.type = 'text';
        input.required = true;
        input.className = 'runner-name-input w-full bg-white/5 border border-white/10 rounded-xl focus:border-stride-volt text-stride-chalk font-light text-sm px-4 py-3 outline-none transition-colors duration-300';
        input.placeholder = (i === 0 && n === 1) ? 'Runner full name' : ('Runner ' + (i + 1) + ' full name');
        
        if (existing[i]) input.value = existing[i];
        else if (i === 0) { const fn = $('fullname'); if (fn) input.value = fn.value.trim(); }
        
        wrap.appendChild(input);
        runnerNamesWrap.appendChild(wrap);
      }
    }

    // Auto-sync booker's name to the first runner name
    (function wireBookerSync() {
      const fn = $('fullname');
      if (!fn || !runnerNamesWrap) return;
      fn.addEventListener('input', function () {
        const first = runnerNamesWrap.querySelector('input.runner-name-input');
        if (first && (first.value.trim() === '' || first.dataset.autofill === '1')) {
          first.value = fn.value.trim();
          first.dataset.autofill = '1';
        }
      });
      runnerNamesWrap.addEventListener('input', function (e) {
        if (e.target && e.target.classList.contains('runner-name-input')) {
          e.target.dataset.autofill = '';
        }
      });
    })();

    // Package change listeners
    function syncPackage() { 
        renderRunnerNameFields(); 
        updateEstimate(); 
    }
    
    pkgSel && pkgSel.addEventListener('change', syncPackage);
    syncPackage();
  
    // Registration pricing + package select buttons on cards
    document.querySelectorAll('.select-package-btn').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const pkg = btn.getAttribute('data-package');
            if (pkg && pkgSel) {
                for (const opt of pkgSel.options) {
                    if (opt.value === pkg || opt.value.startsWith(pkg) || pkg.startsWith(opt.value)) { 
                        pkgSel.value = opt.value; 
                        break; 
                    }
                }
                syncPackage();
                $('register').scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
            }
        });
    });
  
    // --- Form Submission & Modal Flow ---
    form && form.addEventListener('submit', (e) => {
      e.preventDefault();
      
      const terms = $('verify-terms');
      if (terms && !terms.checked) {
        alert('Please confirm the terms and conditions.');
        return;
      }

      const names = currentRunnerNames();
      const guestCount = currentPax();
      
      if (names.length < guestCount || names.some(function (nm) { return !nm; })) {
        alert('Please enter a name for all runners.');
        return;
      }

      pendingPayload = {
        full_name: getVal('fullname'),
        email: getVal('email'),
        phone: getVal('phone'),
        emergency_contact: getVal('emergency'),
        package: pkgSel ? pkgSel.value : '',
        shirt_size: getVal('shirt'),
        guests: guestCount,
        guest_names: names,
        referrer: getVal('referrer') || null,
        total_amount: currentPrice(),
        accept_terms: true,
      };
  
      // Populate Confirm Modal
      setText('confirm-name', pendingPayload.full_name || '—');
      setText('confirm-email', pendingPayload.email || '—');
      setText('confirm-package', pendingPayload.package);
      setText('confirm-shirt', pendingPayload.shirt_size);
      setText('confirm-total', peso(pendingPayload.total_amount));
      
      const refRow = $('confirm-referrer-row');
      const refVal = $('confirm-referrer');
      if (refRow && refVal) {
          if (pendingPayload.referrer) {
              refVal.textContent = pendingPayload.referrer;
              refRow.style.display = 'flex';
          } else {
              refRow.style.display = 'none';
          }
      }
  
      openModal($('confirm-modal'));
    });
  
    const editBtn = $('edit-booking');
    editBtn && editBtn.addEventListener('click', () => closeModal($('confirm-modal')));
  
    const confirmBtn = $('confirm-booking');
    confirmBtn && confirmBtn.addEventListener('click', async () => {
      if (!pendingPayload) return;
      const originalLabel = confirmBtn.textContent;
      setBusy(confirmBtn, true, 'Submitting\u2026');
      
      try {
        const res = await fetch(`${API_BASE}/api/bookings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(pendingPayload),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(extractError(data) || 'Could not submit your request.');
        
        currentBooking = data;
        
        closeModal($('confirm-modal'));
        setText('payment-total-ui', peso(currentBooking.total_amount));
        openModal($('payment-modal')); 

      } catch (err) {
        alert(err.message);
        closeModal($('confirm-modal'));
      } finally {
        setBusy(confirmBtn, false, originalLabel || 'Confirm entry');
      }
    });
  
    const submitRefBtn = $('submit-reference'); 
    submitRefBtn && submitRefBtn.addEventListener('click', async () => {
      if (!currentBooking) return;
      
      const fileInput = $('receipt-upload');
      const file = fileInput ? fileInput.files[0] : null;
      if (!file) return alert('Please upload a screenshot of your payment transfer.');

      const ALLOWED_RECEIPT_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
      const MAX_RECEIPT_SIZE = 10 * 1024 * 1024; // 10 MB
      if (!ALLOWED_RECEIPT_TYPES.includes(file.type)) {
        return alert('Please upload a JPG, PNG, WEBP, or PDF file.');
      }
      if (file.size > MAX_RECEIPT_SIZE) {
        return alert('File too large. Max size is 10MB.');
      }

      const originalLabel = submitRefBtn.textContent;
      setBusy(submitRefBtn, true, 'Uploading\u2026');
      
      const formData = new FormData();
      formData.append('receipt', file);

      try {
        const res = await fetch(`${API_BASE}/api/bookings/${currentBooking.id}/submit-payment`, {
          method: 'POST',
          body: formData, 
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(extractError(data) || 'Could not upload receipt.');

        setText('submitted-name', currentBooking.full_name);
        setText('submitted-package', currentBooking.package);
        setText('submitted-total', peso(currentBooking.total_amount));
        
        closeModal($('payment-modal'));
        openModal($('submitted-modal'));
      } catch (err) {
        alert(err.message);
      } finally {
        setBusy(submitRefBtn, false, originalLabel);
      }
    });

    const finishBtn = $('close-submitted');
    finishBtn && finishBtn.addEventListener('click', () => {
      closeModal($('submitted-modal'));
      
      if (currentBooking) {
        setText('ticket-name', currentBooking.full_name || '—');
        setText('ticket-package', currentBooking.package);
        setText('ticket-shirt', currentBooking.shirt_size);
        setText('ticket-code', 'STR-' + Math.floor(100000 + Math.random() * 900000));
      }
      openModal($('receipt-modal'));
      if (form) form.reset();
    });

    // --- Modal Closing Mechanics ---
    const confirmModalEl = $('confirm-modal');
    const paymentModalEl = $('payment-modal');
    const submittedModalEl = $('submitted-modal');
    const receiptModalEl = $('receipt-modal');
  
    const closeConfirm = $('close-confirm');
    closeConfirm && closeConfirm.addEventListener('click', () => closeModal(confirmModalEl));
    const closePayment = $('close-payment');
    closePayment && closePayment.addEventListener('click', () => closeModal(paymentModalEl));
    const closeReceipt = $('close-receipt');
    closeReceipt && closeReceipt.addEventListener('click', () => closeModal(receiptModalEl));
  
    [confirmModalEl, paymentModalEl, submittedModalEl, receiptModalEl].forEach((m) => {
      m && m.addEventListener('click', (e) => { if (e.target === m) closeModal(m); });
    });
  
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeModal(confirmModalEl);
        closeModal(paymentModalEl);
        closeModal(submittedModalEl);
        closeModal(receiptModalEl);
      }
    });
  
    function extractError(data) {
      if (!data) return '';
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
      return '';
    }
});