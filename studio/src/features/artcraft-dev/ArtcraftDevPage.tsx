// 숨은 개발용 화면 /dev/artcraft — 레일에 없음. ArtCraft 공용 부품(src/vendor/artcraft)이 Fluma 톤으로
// 제대로 그려지는지 한 화면에서 확인한다(Phase 0 기반 점검용).
import { useState } from "react";
import { BrushIcon, MousePointer2Icon, SearchIcon, SparklesIcon, SquareIcon } from "lucide-react";
import { Button } from "@storyteller/ui-button";
import { Tooltip } from "@storyteller/ui-tooltip";
import { PopoverMenu, type PopoverItem } from "@storyteller/ui-popover";
import { Modal } from "@storyteller/ui-modal";
import { Input } from "@storyteller/ui-input";
import { Checkbox } from "@storyteller/ui-checkbox";
import { TabSelector } from "@storyteller/ui-tab-selector";
import { SliderV2 } from "@storyteller/ui-sliderv2";
import { Select, type SelectValue } from "@storyteller/ui-select";
import { Badge } from "@storyteller/ui-badge";
import { LoadingSpinner } from "@storyteller/ui-loading-spinner";
import { ButtonIconSelect } from "@storyteller/ui-button-icon-select";
import { Label } from "@storyteller/ui-label";
import { ClassyModelSelector, ModelPage, useCanvas2dPageModelList } from "@storyteller/ui-model-selector";
import { useArtcraftRoot } from "../../vendor/artcraft/_theme/useArtcraftRoot";

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="flex flex-col gap-3 rounded-[8px] border border-ui-panel-border bg-ui-panel p-4">
    <h2 className="hud-label">{title}</h2>
    <div className="flex flex-wrap items-center gap-3">{children}</div>
  </section>
);

export function ArtcraftDevPage() {
  useArtcraftRoot();
  const [modal, setModal] = useState(false);
  const [checked, setChecked] = useState(true);
  const [tab, setTab] = useState("image");
  const [slider, setSlider] = useState(40);
  const [sel, setSel] = useState<SelectValue>("9:16");
  const [items, setItems] = useState<PopoverItem[]>([
    { label: "9:16 세로", selected: true },
    { label: "1:1 정사각", selected: false },
    { label: "16:9 가로", selected: false },
  ]);
  const models = useCanvas2dPageModelList();

  return (
    <div className="ac-root fixed inset-0 z-50 overflow-auto bg-background p-8 text-base-fg" data-testid="artcraft-dev">
      <div className="mx-auto flex max-w-[960px] flex-col gap-4">
        <header className="flex items-center justify-between">
          <h1 className="font-display text-2xl">ArtCraft 부품 · Fluma 톤</h1>
          <Badge label="Phase 0" icon={<SparklesIcon className="h-3 w-3" />} />
        </header>

        <Section title="Button">
          <Button variant="primary">기본 행동</Button>
          <Button variant="secondary">보조</Button>
          <Button variant="action" icon={BrushIcon}>
            액션
          </Button>
          <Button variant="destructive">삭제</Button>
          <Button variant="ghost">고스트</Button>
          <Button variant="primary" loading>
            생성 중
          </Button>
          <Button variant="secondary" disabled>
            비활성
          </Button>
        </Section>

        <Section title="Tooltip · Popover · Modal">
          <Tooltip content="툴팁 내용" position="top">
            <Button variant="action">툴팁 (hover)</Button>
          </Tooltip>
          <PopoverMenu
            items={items}
            mode="toggle"
            panelTitle="화면 비율"
            onSelect={(it) => setItems((xs) => xs.map((x) => ({ ...x, selected: x.label === it.label })))}
          />
          <Button variant="secondary" onClick={() => setModal(true)}>
            모달 열기
          </Button>
          <ClassyModelSelector items={models} page={ModelPage.Canvas2D} panelTitle="모델" />
        </Section>

        <Section title="Input · Checkbox · Select">
          <div className="w-64">
            <Input label="제목" placeholder="장면 제목" icon={SearchIcon} />
          </div>
          <Checkbox label="자막 켜기" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          <div className="w-48">
            <Label>비율</Label>
            <Select
              value={sel}
              onChange={setSel}
              options={[
                { label: "9:16", value: "9:16" },
                { label: "1:1", value: "1:1" },
                { label: "16:9", value: "16:9" },
              ]}
            />
          </div>
        </Section>

        <Section title="TabSelector · SliderV2 · ButtonIconSelect">
          <TabSelector
            tabs={[
              { id: "image", label: "이미지" },
              { id: "video", label: "영상" },
              { id: "3d", label: "3D" },
            ]}
            activeTab={tab}
            onTabChange={setTab}
          />
          <div className="w-64">
            <SliderV2 min={0} max={100} step={1} value={slider} onChange={setSlider} showTooltip suffix="%" />
          </div>
          <ButtonIconSelect
            options={[
              { value: "select", icon: MousePointer2Icon, tooltip: "선택" },
              { value: "brush", icon: BrushIcon, tooltip: "붓" },
              { value: "rect", icon: SquareIcon, tooltip: "사각형" },
            ]}
          />
        </Section>

        <Section title="Badge · LoadingSpinner · 클래스">
          <Badge label="새로 만듦" />
          <Badge label="Antigravity" className="border-primary-400/40 text-primary-200" />
          <LoadingSpinner className="h-6 w-6" />
          <div className="glass px-3 py-2 text-sm">.glass 표면</div>
          <button className="filter-tab active">filter-tab</button>
          <button className="filter-tab">filter-tab</button>
          <div className="h-10 w-40 animate-shimmer rounded-md bg-ui-controls" />
          <div className="bg-dots h-10 w-40 rounded-md border border-ui-panel-border" />
        </Section>
      </div>

      <Modal isOpen={modal} onClose={() => setModal(false)} title="모달 제목">
        <div className="flex flex-col gap-3 text-sm text-base-fg/80">
          <p>ArtCraft Modal 이 Fluma 면 · 선 · 모서리로 그려집니다.</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setModal(false)}>
              취소
            </Button>
            <Button variant="primary" onClick={() => setModal(false)}>
              확인
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
