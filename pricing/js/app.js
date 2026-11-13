/**
 * SYSTEMIZE — Step-by-Step Presentation Wizard & Cost Estimator
 * Direct, Fast, Zero Fluff
 */

document.addEventListener('DOMContentLoaded', () => {
  initPresentationWizard();
  initBottomOnlyPill();
});

function initPresentationWizard() {
  const wizardPanels = document.querySelectorAll('.wizard-step-panel');
  const currentStepNumEl = document.getElementById('current-step-num');
  const totalStepsNumEl = document.getElementById('total-steps-num');
  const wizardStepTitleEl = document.getElementById('wizard-step-title');
  const progressBar = document.getElementById('wizard-progress');
  const btnPrev = document.getElementById('btn-wizard-prev');
  const btnNext = document.getElementById('btn-wizard-next');
  const wizardNavBar = document.getElementById('wizard-nav-bar');
  const stepDots = document.querySelectorAll('#wizard-dots .dot');

  // Summary Elements
  const sumSoftwareName = document.getElementById('sum-software-name');
  const sumSoftwarePrice = document.getElementById('sum-software-price');
  const sumAddonsList = document.getElementById('sum-addons-list');
  const wizardTotalDisplay = document.getElementById('wizard-total-display');
  const pillPriceVal = document.getElementById('pill-price-val');
  const btnWizardWhatsapp = document.getElementById('btn-wizard-whatsapp');
  const pillWhatsappLink = document.getElementById('pill-whatsapp-link');
  const btnRestartWizard = document.getElementById('btn-restart-wizard');

  let currentStep = 1;
  const totalSteps = 6;

  // State object
  const configState = {
    softwarePlan: 'monthly', // 'monthly' (550) or 'annual' (5000)
    softwarePrice: 550,
    softwareLabel: 'باقة البرنامج: تثبيت 3 شهور (550 ج.م/شهر)',
    addons: {
      face: { selected: true, price: 6000, name: 'بصمة وجه ذكية (شامل الكاميرا والربط)' },
      whatsapp: { selected: true, price: 1500, name: 'مرسل رسائل الواتساب الآلي' },
      telegram: { selected: false, price: 2000, name: 'بوت تليجرام الذكي للتقارير' },
      lock: { selected: false, price: 0, name: 'بدون كالون' },
      pc: { selected: false, price: 0, name: 'كمبيوتر العميل المعتمد' }
    }
  };

  const stepTitles = {
    1: 'الخطوة 1: اختيار باقة البرنامج الأساسي',
    2: 'الخطوة 2: بصمة الوجه الذكية للبوابات',
    3: 'الخطوة 3: مرسل رسائل وتنبيهات الواتساب',
    4: 'الخطوة 4: بوت تليجرام لتقارير الخزينة',
    5: 'الخطوة 5: كالون الباب الإلكتروني',
    6: 'الخطوة 6: توريد جهاز الكمبيوتر',
    summary: 'الملخص النهائي وعرض السعر'
  };

  function formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(num);
  }

  function calculateGrandTotal() {
    let total = configState.softwarePrice;
    const activeAddons = [];

    if (configState.addons.face.selected) {
      total += configState.addons.face.price;
      activeAddons.push(configState.addons.face);
    }
    if (configState.addons.whatsapp.selected) {
      total += configState.addons.whatsapp.price;
      activeAddons.push(configState.addons.whatsapp);
    }
    if (configState.addons.telegram.selected) {
      total += configState.addons.telegram.price;
      activeAddons.push(configState.addons.telegram);
    }
    if (configState.addons.lock.selected && configState.addons.lock.price > 0) {
      total += configState.addons.lock.price;
      activeAddons.push(configState.addons.lock);
    }
    if (configState.addons.pc.selected && configState.addons.pc.price > 0) {
      total += configState.addons.pc.price;
      activeAddons.push(configState.addons.pc);
    }

    return { total, activeAddons };
  }

  function updateSummaryDisplay() {
    const { total, activeAddons } = calculateGrandTotal();

    sumSoftwareName.textContent = configState.softwareLabel;
    sumSoftwarePrice.textContent = `${formatNumber(configState.softwarePrice)} ج.م`;

    sumAddonsList.innerHTML = '';
    if (activeAddons.length === 0) {
      sumAddonsList.innerHTML = '<div class="summary-line"><span class="item-name" style="color: var(--text-dim);">بدون إضافات أخرى مختارة</span><span class="item-val">0 ج.م</span></div>';
    } else {
      activeAddons.forEach(item => {
        const row = document.createElement('div');
        row.className = 'summary-line';
        row.innerHTML = `<span class="item-name">+ ${item.name}</span><span class="item-val">${formatNumber(item.price)} ج.م</span>`;
        sumAddonsList.appendChild(row);
      });
    }

    const formattedTotal = formatNumber(total);
    wizardTotalDisplay.textContent = formattedTotal;
    if (pillPriceVal) pillPriceVal.textContent = formattedTotal;
  }

  function showStep(step) {
    wizardPanels.forEach(p => p.classList.remove('active'));

    if (step === 'summary') {
      const summaryPanel = document.getElementById('step-summary-view');
      if (summaryPanel) summaryPanel.classList.add('active');
      wizardStepTitleEl.textContent = stepTitles.summary;
      currentStepNumEl.textContent = '6';
      progressBar.style.width = '100%';
      wizardNavBar.style.display = 'none';
      updateSummaryDisplay();
      return;
    }

    wizardNavBar.style.display = 'flex';
    const targetPanel = document.querySelector(`.wizard-step-panel[data-step="${step}"]`);
    if (targetPanel) targetPanel.classList.add('active');

    currentStepNumEl.textContent = step;
    wizardStepTitleEl.textContent = stepTitles[step] || '';

    // Update progress
    const pct = ((step - 1) / (totalSteps - 1)) * 100;
    progressBar.style.width = `${Math.max(16, pct)}%`;

    // Navigation buttons visibility
    btnPrev.style.visibility = step > 1 ? 'visible' : 'hidden';
    btnNext.textContent = step === totalSteps ? 'عرض الملخص النهائي ←' : 'الخطوة التالية ←';

    // Update dots
    stepDots.forEach((dot, idx) => {
      if (idx + 1 === step) {
        dot.classList.add('active');
      } else {
        dot.classList.remove('active');
      }
    });
  }

  // Next & Prev button listeners
  btnNext.addEventListener('click', () => {
    if (currentStep < totalSteps) {
      currentStep++;
      showStep(currentStep);
    } else {
      showStep('summary');
    }
  });

  btnPrev.addEventListener('click', () => {
    if (currentStep > 1) {
      currentStep--;
      showStep(currentStep);
    }
  });

  // Next step shortcut buttons inside step panels
  document.querySelectorAll('.btn-next-step').forEach(btn => {
    btn.addEventListener('click', () => {
      const nextStep = parseInt(btn.getAttribute('data-next'), 10);
      currentStep = nextStep;
      showStep(currentStep);
    });
  });

  const btnFinish = document.getElementById('btn-show-summary');
  if (btnFinish) {
    btnFinish.addEventListener('click', () => {
      showStep('summary');
    });
  }

  if (btnRestartWizard) {
    btnRestartWizard.addEventListener('click', () => {
      currentStep = 1;
      showStep(currentStep);
    });
  }

  // --- Step 1: Software Plan Radios ---
  const softwareRadios = document.querySelectorAll('.software-radio');
  softwareRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.software-opt-card').forEach(c => c.classList.remove('selected'));
      radio.closest('.software-opt-card').classList.add('selected');

      if (radio.value === 'monthly') {
        configState.softwarePlan = 'monthly';
        configState.softwarePrice = 550;
        configState.softwareLabel = 'باقة البرنامج: تثبيت 3 شهور (550 ج.م/شهر)';
      } else {
        configState.softwarePlan = 'annual';
        configState.softwarePrice = 5000;
        configState.softwareLabel = 'باقة البرنامج: عرض الخصم السنوي (5,000 ج.م/سنة)';
      }
    });
  });

  // --- Steps 2, 3, 4: Yes / No Choice Buttons ---
  document.querySelectorAll('.btn-choice-skip, .btn-choice-add').forEach(btn => {
    btn.addEventListener('click', () => {
      const addonKey = btn.getAttribute('data-addon');
      const action = btn.getAttribute('data-action');
      const parentStep = btn.closest('.wizard-step-panel');
      const stepNum = parseInt(parentStep.getAttribute('data-step'), 10);

      if (action === 'add') {
        configState.addons[addonKey].selected = true;
      } else {
        configState.addons[addonKey].selected = false;
      }

      // Automatically advance to the next step
      if (stepNum < totalSteps) {
        currentStep = stepNum + 1;
        showStep(currentStep);
      } else {
        showStep('summary');
      }
    });
  });

  // --- Step 5: Lock Radios ---
  const lockRadios = document.querySelectorAll('.lock-radio');
  lockRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.lock-opt-card').forEach(c => c.classList.remove('selected'));
      radio.closest('.lock-opt-card').classList.add('selected');

      const price = parseInt(radio.value, 10);
      const name = radio.getAttribute('data-name') || 'بدون كالون';

      configState.addons.lock.selected = price > 0;
      configState.addons.lock.price = price;
      configState.addons.lock.name = name;
    });
  });

  // --- Step 6: PC Radios ---
  const pcRadios = document.querySelectorAll('.pc-radio');
  pcRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.pc-opt-card').forEach(c => c.classList.remove('selected'));
      radio.closest('.pc-opt-card').classList.add('selected');

      const price = parseInt(radio.value, 10);
      const name = radio.getAttribute('data-name') || 'كمبيوتر العميل الحالي';

      configState.addons.pc.selected = price > 0;
      configState.addons.pc.price = price;
      configState.addons.pc.name = name;
    });
  });

  // --- WhatsApp Lead Dispatch ---
  function generateWhatsAppUrl() {
    const { total, activeAddons } = calculateGrandTotal();

    let msg = `*طلب تجهيز وتشغيل نظام SYSTEMIZE لإدارة الجيم*\n\n`;
    msg += `لقد قمت باختيار وتحديد التجهيز التالي لجيمي:\n`;
    msg += `• ${configState.softwareLabel}\n`;

    if (activeAddons.length > 0) {
      msg += `\n*الإضافات والأجهزة المختارة:*\n`;
      activeAddons.forEach((item, idx) => {
        msg += `${idx + 1}. ${item.name} — ${formatNumber(item.price)} ج.م\n`;
      });
    }

    msg += `\n*إجمالي التجهيز التقديري: ${formatNumber(total)} جنيه مصري.*\n\n`;
    msg += `يرجى التواصل معي لتنسيق موعد التنصيب وبدء التشغيل الفوري.`;

    return `https://wa.me/201000000000?text=${encodeURIComponent(msg)}`;
  }

  if (btnWizardWhatsapp) {
    btnWizardWhatsapp.addEventListener('click', () => {
      window.open(generateWhatsAppUrl(), '_blank');
    });
  }

  if (pillWhatsappLink) {
    pillWhatsappLink.addEventListener('click', (e) => {
      e.preventDefault();
      window.open(generateWhatsAppUrl(), '_blank');
    });
  }

  // Initial step setup
  showStep(1);
}

/**
 * Show the floating pill ONLY when the user reaches near the bottom of the page
 */
function initBottomOnlyPill() {
  const bottomPill = document.getElementById('bottom-pill');
  if (!bottomPill) return;

  function checkScrollPosition() {
    const scrollY = window.scrollY || window.pageYOffset;
    const viewportHeight = window.innerHeight;
    const fullHeight = document.documentElement.scrollHeight;

    const distanceToBottom = fullHeight - (scrollY + viewportHeight);

    // Show only when user has reached near bottom (within 650px of bottom or >82% of page)
    if (distanceToBottom < 650 || (scrollY + viewportHeight) / fullHeight > 0.82) {
      bottomPill.classList.add('is-visible');
    } else {
      bottomPill.classList.remove('is-visible');
    }
  }

  window.addEventListener('scroll', checkScrollPosition, { passive: true });
  window.addEventListener('resize', checkScrollPosition);
  checkScrollPosition();
}
