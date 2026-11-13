import { Notice } from "@/components/ui/notice";

/** TODO(owner): Q10 — 오너 검토·법률 검토 후 이 안내를 제거한다. */
export function LegalDraftNote() {
  return (
    <Notice tone="info" title="검토 중인 초안이에요" className="mb-10">
      이 문서는 서비스 운영자가 작성한 초안이며 법률 자문을 거치지 않았어요. 내용은 바뀔 수 있어요.
    </Notice>
  );
}
